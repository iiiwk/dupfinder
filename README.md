# DupFinder

A simple and fast duplicate file finder & remover for personal use, powered by a C++ scanning engine and a Python GUI.

[中文文档](README_CN.md)

> **Disclaimer**: This is a personal utility, not a production-grade product. It has only been tested on a personal PC with tens of thousands of files under **Windows 10 22H2**. Please back up your data before use.
>
> Bug reports and compatibility feedback are welcome via Issues, though I may not always have the bandwidth to address them. The codebase is intentionally small and straightforward — pull requests for new features, improvements, or platform support are very much appreciated!

## Screenshot

![English UI](images/ui_en.png)

## Features

- **Three-stage high-speed scan**: file-size grouping → quick hash (xxHash, first 4 KB) → full/sampled hash (xxHash 128-bit); large files are sampled at head / middle / tail only
- **OpenMP multi-threaded** hash computation
- **GUI**: scan, browse, and delete in one place; supports recycle-bin or permanent deletion
- **Bilingual UI** (Chinese / English), switchable at runtime
- **Multiple themes** with auto-saved preferences

## Build & Install

### Prerequisites

- Windows 10/11
- Visual Studio with C++ Desktop Development workload (tested with VS 2022)
- CMake ≥ 3.14
- Python ≥ 3.10

### One-click Build

```bat
build_and_install.bat
```

The script runs CMake configure → build → install to `install/`, then installs Python dependencies.

### Manual Build

```bat
cmake -B build -A x64 -DCMAKE_INSTALL_PREFIX=install
cmake --build build --config Release
cmake --install build --config Release
pip install -r requirements.txt
```

### Run

```bat
python install\dupfinder_ui.py
```

## Project Structure

```
├── src/dupfinder_main.cpp    # C++ scan engine
├── dupfinder_ui.py           # Python GUI
├── dupfinder_strings.json    # i18n string resources
├── font/                     # UI font files
├── CMakeLists.txt            # Build script
├── build_and_install.bat     # One-click build script
├── requirements.txt          # Python dependencies
└── thirdparty/xxhash/        # xxHash source
```

## Acknowledgements

- [xxHash](https://github.com/Cyan4973/xxHash) — extremely fast hash algorithm, BSD-2-Clause license
- [HarmonyOS Sans SC](https://developer.huawei.com/consumer/en/design/resource/) — Huawei HarmonyOS design font, included in the `font/` directory and subject to its official license

## Development

Code and documentation were written with the assistance of **Claude Opus 4** in the [Cursor](https://www.cursor.com/) IDE.

## License

[MIT](LICENSE)
