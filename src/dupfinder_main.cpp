#include <xxhash.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <unordered_map>
#include <vector>

#include <omp.h>

#ifdef _WIN32
#include <windows.h>
#include <fcntl.h>
#include <io.h>
#endif

namespace fs = std::filesystem;

// ============================================================
// Constants
// ============================================================
constexpr size_t QUICK_HASH_SIZE   = 4 * 1024;         // 4 KB  -- first-pass quick hash
constexpr size_t SAMPLE_THRESHOLD  = 1 * 1024 * 1024;  // 1 MB  -- above this, use sampling
constexpr size_t SAMPLE_BLOCK_SIZE = 64 * 1024;         // 64 KB -- per-sample block
constexpr size_t READ_BUF_SIZE     = 256 * 1024;        // 256 KB read buffer

struct FileEntry {
    fs::path    path;
    uintmax_t   size;
};

// ============================================================
// Hash computation (thread-safe -- no shared state)
// ============================================================

static uint64_t quick_hash(const fs::path& p) {
    std::ifstream f(p, std::ios::binary);
    if (!f) return 0;

    char buf[QUICK_HASH_SIZE];
    f.read(buf, QUICK_HASH_SIZE);
    auto n = f.gcount();
    return XXH3_64bits(buf, static_cast<size_t>(n));
}

static XXH128_hash_t full_hash(const fs::path& p, uintmax_t file_size) {
    std::ifstream f(p, std::ios::binary);
    if (!f) return {0, 0};

    if (file_size <= SAMPLE_THRESHOLD) {
        XXH3_state_t* state = XXH3_createState();
        XXH3_128bits_reset(state);

        char buf[READ_BUF_SIZE];
        while (f.read(buf, READ_BUF_SIZE) || f.gcount() > 0) {
            XXH3_128bits_update(state, buf, static_cast<size_t>(f.gcount()));
            if (f.eof()) break;
        }
        auto h = XXH3_128bits_digest(state);
        XXH3_freeState(state);
        return h;
    }

    // Large file -- three-segment sampling: head / middle / tail
    XXH3_state_t* state = XXH3_createState();
    XXH3_128bits_reset(state);

    char buf[SAMPLE_BLOCK_SIZE];

    XXH3_128bits_update(state, &file_size, sizeof(file_size));

    f.seekg(0);
    f.read(buf, SAMPLE_BLOCK_SIZE);
    XXH3_128bits_update(state, buf, static_cast<size_t>(f.gcount()));

    auto mid = static_cast<std::streamoff>(file_size / 2 - SAMPLE_BLOCK_SIZE / 2);
    f.seekg(mid);
    f.read(buf, SAMPLE_BLOCK_SIZE);
    XXH3_128bits_update(state, buf, static_cast<size_t>(f.gcount()));

    auto tail = static_cast<std::streamoff>(file_size - SAMPLE_BLOCK_SIZE);
    f.seekg(tail);
    f.read(buf, SAMPLE_BLOCK_SIZE);
    XXH3_128bits_update(state, buf, static_cast<size_t>(f.gcount()));

    auto h = XXH3_128bits_digest(state);
    XXH3_freeState(state);
    return h;
}

// ============================================================
// Formatting utilities
// ============================================================

static std::string hash_to_hex(XXH128_hash_t h) {
    char buf[33];
    std::snprintf(buf, sizeof(buf), "%016llx%016llx",
                  static_cast<unsigned long long>(h.high64),
                  static_cast<unsigned long long>(h.low64));
    return buf;
}

static std::string human_size(uintmax_t bytes) {
    const char* units[] = {"B", "KB", "MB", "GB", "TB"};
    double      val     = static_cast<double>(bytes);
    int         idx     = 0;
    while (val >= 1024.0 && idx < 4) {
        val /= 1024.0;
        ++idx;
    }
    char buf[64];
    if (idx == 0)
        std::snprintf(buf, sizeof(buf), "%llu B", static_cast<unsigned long long>(bytes));
    else
        std::snprintf(buf, sizeof(buf), "%.2f %s", val, units[idx]);
    return buf;
}

// ============================================================
// Main
// ============================================================

#ifdef _WIN32
int wmain(int argc, wchar_t* argv[]) {
    SetConsoleOutputCP(CP_UTF8);
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stderr), _O_BINARY);

    fs::path root = fs::current_path();
    bool sort_by_size = false;

    for (int i = 1; i < argc; ++i) {
        std::wstring arg = argv[i];
        if (arg == L"--sort=size")      { sort_by_size = true; }
        else if (arg == L"--sort=path") { sort_by_size = false; }
        else                            { root = fs::path(argv[i]); }
    }
#else
int main(int argc, char* argv[]) {
    fs::path root = fs::current_path();
    bool sort_by_size = false;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--sort=size")       { sort_by_size = true; }
        else if (arg == "--sort=path")  { sort_by_size = false; }
        else                            { root = fs::path(argv[i]); }
    }
#endif

    if (!fs::is_directory(root)) {
        std::cerr << "Error: " << root.u8string() << " is not a directory.\n";
        return 1;
    }

    int num_threads = omp_get_max_threads();
    auto t0 = std::chrono::steady_clock::now();

    // -- Stage 1: collect files and group by size (single-threaded, metadata only) --
    std::unordered_map<uintmax_t, std::vector<FileEntry>> size_groups;
    size_t total_files = 0;
    size_t skipped     = 0;

    for (auto& entry : fs::recursive_directory_iterator(root, fs::directory_options::skip_permission_denied)) {
        if (!entry.is_regular_file()) continue;
        std::error_code ec;
        auto sz = entry.file_size(ec);
        if (ec) { ++skipped; continue; }
        if (sz == 0) continue;
        size_groups[sz].push_back({entry.path(), sz});
        ++total_files;
    }

    // Remove unique-size groups (cannot be duplicates)
    size_t candidates_after_size = 0;
    for (auto it = size_groups.begin(); it != size_groups.end(); ) {
        if (it->second.size() < 2)
            it = size_groups.erase(it);
        else {
            candidates_after_size += it->second.size();
            ++it;
        }
    }

    // -- Stage 2: quick hash (first 4KB) -- OpenMP parallel --
    // Flatten into contiguous vector for parallel for
    std::vector<FileEntry> candidates;
    candidates.reserve(candidates_after_size);
    for (auto& [sz, files] : size_groups)
        for (auto& fe : files)
            candidates.push_back(std::move(fe));

    size_t n_cand = candidates.size();
    std::vector<uint64_t> quick_hashes(n_cand);

    #pragma omp parallel for schedule(dynamic, 4)
    for (int64_t i = 0; i < static_cast<int64_t>(n_cand); ++i) {
        auto qh = quick_hash(candidates[i].path);
        quick_hashes[i] = XXH3_64bits_withSeed(&qh, sizeof(qh), candidates[i].size);
    }

    // Group + prune
    std::unordered_map<uint64_t, std::vector<size_t>> quick_groups;
    for (size_t i = 0; i < n_cand; ++i)
        quick_groups[quick_hashes[i]].push_back(i);

    // Flatten stage-3 candidate indices
    std::vector<size_t> stage3_indices;
    for (auto& [key, indices] : quick_groups) {
        if (indices.size() >= 2)
            for (auto idx : indices)
                stage3_indices.push_back(idx);
    }

    // -- Stage 3: full / sampled hash -- OpenMP parallel --
    size_t n_full = stage3_indices.size();
    std::vector<XXH128_hash_t> full_hashes(n_full);

    #pragma omp parallel for schedule(dynamic, 2)
    for (int64_t i = 0; i < static_cast<int64_t>(n_full); ++i) {
        auto idx = stage3_indices[i];
        full_hashes[i] = full_hash(candidates[idx].path, candidates[idx].size);
    }

    // Group by full hash
    struct DupGroup {
        XXH128_hash_t hash;
        uintmax_t     size;
        std::vector<fs::path> paths;
    };

    std::unordered_map<std::string, DupGroup> dup_map;
    for (size_t i = 0; i < n_full; ++i) {
        auto hex = hash_to_hex(full_hashes[i]);
        auto idx = stage3_indices[i];
        auto& grp = dup_map[hex];
        grp.hash = full_hashes[i];
        grp.size = candidates[idx].size;
        grp.paths.push_back(candidates[idx].path);
    }

    // Filter out actual duplicate groups
    std::vector<DupGroup> duplicates;
    for (auto& [hex, grp] : dup_map) {
        if (grp.paths.size() >= 2) {
            std::sort(grp.paths.begin(), grp.paths.end());
            duplicates.push_back(std::move(grp));
        }
    }

    if (sort_by_size) {
        std::sort(duplicates.begin(), duplicates.end(),
                  [](const DupGroup& a, const DupGroup& b) { return a.size > b.size; });
    } else {
        std::sort(duplicates.begin(), duplicates.end(),
                  [](const DupGroup& a, const DupGroup& b) {
                      return a.paths.front() < b.paths.front();
                  });
    }

    auto t1 = std::chrono::steady_clock::now();
    double elapsed = std::chrono::duration<double, std::milli>(t1 - t0).count();

    // -- Output results --
    std::string output;
    output.reserve(4096);

    output += "========================================\n";
    output += "  DupFinder - Duplicate File Report\n";
    output += "========================================\n";
    output += "Scan Directory: " + root.u8string() + "\n";
    output += "Threads: " + std::to_string(num_threads) + "\n";
    output += "Total Files: " + std::to_string(total_files) + "\n";
    output += "Candidates: " + std::to_string(candidates_after_size) + "\n";
    output += "Quick Hash: " + std::to_string(n_cand) + "\n";
    output += "Full Hash: " + std::to_string(n_full) + "\n";
    output += std::string("Sort: ") + (sort_by_size ? "by_size" : "by_path") + "\n";
    char elapsed_buf[64];
    std::snprintf(elapsed_buf, sizeof(elapsed_buf), "%.1f ms", elapsed);
    output += "Elapsed: " + std::string(elapsed_buf) + "\n";

    if (duplicates.empty()) {
        output += "\n✓ No duplicates found.\n";
    } else {
        uintmax_t wasted = 0;
        for (auto& g : duplicates) wasted += g.size * (g.paths.size() - 1);

        output += "Dup Groups: " + std::to_string(duplicates.size()) + "\n";
        output += "Reclaimable: " + human_size(wasted) + "\n";
        output += "----------------------------------------\n\n";

        int group_no = 0;
        for (auto& grp : duplicates) {
            ++group_no;
            auto hex = hash_to_hex(grp.hash);

            output += "[" + std::to_string(group_no) + "] ";
            output += human_size(grp.size);
            output += "  x" + std::to_string(grp.paths.size()) + " copies";
            if (grp.size > SAMPLE_THRESHOLD) output += "  (sampled)";
            output += "\n";
            output += "    Hash: " + hex + "\n";

            for (auto& p : grp.paths) {
                auto rel = fs::relative(p, root);
                output += "      → " + rel.u8string() + "\n";
            }
            output += "\n";
        }
    }

    output += "========================================\n";

    fwrite(output.data(), 1, output.size(), stdout);
    fflush(stdout);

    return 0;
}
