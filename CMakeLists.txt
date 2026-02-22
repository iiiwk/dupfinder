cmake_minimum_required(VERSION 3.14)
project(dupfinder LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(MSVC)
    add_compile_options(/utf-8)
    add_compile_options("$<$<CONFIG:Release>:/O2;/DNDEBUG>")
else()
    add_compile_options("$<$<CONFIG:Release>:-O3;-march=native;-DNDEBUG>")
endif()

find_package(OpenMP REQUIRED)

# xxHash -- build from local source (single file)
add_library(xxhash STATIC thirdparty/xxhash/xxhash.c)
target_include_directories(xxhash PUBLIC thirdparty/xxhash)

add_executable(dupfinder src/dupfinder_main.cpp)
target_link_libraries(dupfinder PRIVATE xxhash OpenMP::OpenMP_CXX)

if(WIN32)
    target_compile_definitions(dupfinder PRIVATE _CRT_SECURE_NO_WARNINGS UNICODE _UNICODE)
endif()

# -- Install rules --
install(TARGETS dupfinder RUNTIME DESTINATION .)
install(FILES
    dupfinder_ui.py
    dupfinder_strings.json
    requirements.txt
    DESTINATION .
)
install(DIRECTORY font DESTINATION . OPTIONAL)
