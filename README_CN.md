# DupFinder — 重复文件查找与删除工具

一个供个人使用的重复文件筛选删除小工具，由 C++ 高性能扫描引擎 + Python GUI 界面组成。

> **声明**：本项目是个人用途的小工具，没有经过充分的产品化测试，仅在个人电脑上针对几万份文件的场景使用过，测试环境为 **Windows 10 22H2**。请在使用前做好数据备份。
>
> 如果遇到功能或兼容性问题，欢迎通过 Issues 反馈，但作者不一定有精力及时维护或修复。代码逻辑和结构都比较简单，非常欢迎大家提交 PR 来补全或增强功能！

## 截图

![中文界面](images/ui_cn.png)

## 功能

- **三阶段高速扫描**：文件大小分组 → 快速哈希 (xxHash, 前 4KB) → 完整/采样哈希 (xxHash 128-bit)，大文件仅采样头/中/尾三段
- **OpenMP 多线程**加速哈希计算
- **GUI 界面**：扫描、浏览、删除一体化操作；支持删除到回收站或永久删除
- **中/英双语**界面，可动态切换
- **多主题**支持，偏好自动保存

## 构建与安装

### 环境要求

- Windows 10/11
- Visual Studio（需含 C++ 桌面开发工作负载；测试环境为 VS 2022）
- CMake ≥ 3.14
- Python ≥ 3.10

### 一键构建

```bat
build_and_install.bat
```

脚本会依次完成 CMake 配置、编译、安装到 `install/` 目录，以及安装 Python 依赖。

### 手动构建

```bat
cmake -B build -A x64 -DCMAKE_INSTALL_PREFIX=install
cmake --build build --config Release
cmake --install build --config Release
pip install -r requirements.txt
```

### 运行

```bat
python install\dupfinder_ui.py
```

## 项目结构

```
├── src/dupfinder_main.cpp    # C++ 扫描引擎
├── dupfinder_ui.py           # Python GUI
├── dupfinder_strings.json    # 国际化语言资源
├── font/                     # 界面字体文件
├── CMakeLists.txt            # 构建脚本
├── build_and_install.bat     # 一键构建脚本
├── requirements.txt          # Python 依赖
└── thirdparty/xxhash/        # xxHash 源码
```

## 致谢与第三方资源

- [xxHash](https://github.com/Cyan4973/xxHash) — 极速哈希算法，BSD-2-Clause 许可
- [HarmonyOS Sans SC](https://developer.huawei.com/consumer/en/design/resource/) — 华为 HarmonyOS 设计字体资源，已包含在仓库 `font/` 目录中，该字体遵循其官方许可协议

## 开发说明

本项目的代码与文档在 [Cursor](https://www.cursor.com/) IDE 中借助 **Claude Opus 4** 模型辅助完成。

## License

[MIT](LICENSE)
