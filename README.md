# YuQue-BdT

![](assets/YuQue-BdT-logo.png)

[![GitHub Release](https://img.shields.io/github/v/release/Be1k0/YuQue-BdT?logo=github&sort=semver&label=Latest%20Release)](https://github.com/Be1k0/YuQue-BdT/releases/latest) [![Total Downloads](https://img.shields.io/github/downloads/Be1k0/YuQue-BdT/total?logo=github&label=Downloads)](https://github.com/Be1k0/YuQue-BdT/releases) [![License](https://img.shields.io/github/license/Be1k0/YuQue-BdT?label=License)](LICENSE) [![GitHub Stars](https://img.shields.io/github/stars/Be1k0/YuQue-BdT?logo=github&style=flat&label=Stars)](https://github.com/Be1k0/YuQue-BdT/stargazers) [![Last Commit](https://img.shields.io/github/last-commit/Be1k0/YuQue-BdT?logo=github&label=Last%20Commit)](https://github.com/Be1k0/YuQue-BdT/commits/main) [![Python Version](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/) [![Platform Support](https://img.shields.io/badge/platform-Windows%20%7C%20Ubuntu-0078D4?logo=windows&logoColor=white)](https://github.com/Be1k0/YuQue-BdT#环境要求)

## 简介

YuQue-BdT 是一款针对语雀开发的知识库批量导出 GUI 工具，采用Python开发，支持一键导出个人账号下全类型的知识库文档，同时也可下载他人公开的语雀知识库。软件开源免费，致力于帮助用户更方便地备份和迁移语雀上的知识内容。

项目初衷源于作者自身有将语雀文档迁移导出至本地这方面的需求。但官方提供一键导出功能仅支持导出pdf和语雀自带格式，且现有同类工具又大多以 CLI 终端操作为主又或者是年久失修，对于部分人来说其实不太友好，便利用空余时间开发了这款带有现代化GUI界面的版本

## 功能特点

### 账号与知识库管理

- 支持账号密码登录、网页登录两种方式，自动持久化登录状态
- 自动获取并展示个人所有知识库，支持批量选择导出
- 支持导出指定文档层级，可导出他人公开知识库
- 智能缓存知识库信息，提升加载速度

### 知识库批量导出与文档处理

| 类型   | 个人知识库可导出格式 | 公开知识库可导出格式 |
| ------ | -------------------- | -------------------- |
| 文档   | Markdown、PDF、Word  | Markdown             |
| 画板   | PNG                  | PNG                  |
| 表格   | XLSX                 | 暂不支持             |
| 数据表 | XLSX                 | 暂不支持             |

- 导出会完整保留语雀原有的层级结构
- 支持保留或移除语雀特有换行标识
- 智能跳过已下载文件，支持增量更新导出

### 文件处理

- Markdown格式下支持下载文档中的所有图片、视频等文件，自动处理语雀相关文件链接，确保本地可访问
- 支持多线程并发下载，导出更快更高效

### 用户界面

- 现代化图形界面，操作直观简洁
- 支持亮色、暗色主题及跟随系统主题切换
- 实时显示导出进度、状态与运行日志
- 支持自定义导出目录，内置版本检查与一键更新功能

## 界面预览

![image-20260407214202152](assets/image-20260407214202152.png)

![image-20260407214231899](assets/image-20260407214231899.png)

![image-20260407214256714](assets/image-20260407214256714.png)

![image-20260407214309639](assets/image-20260407214309639.png)

![image-20260407214328777](assets/image-20260407214328777.png)

![image-20260407214342867](assets/image-20260407214342867.png)

![image-20260407214356748](assets/image-20260407214356748.png)

![image-20260407214435666](assets/image-20260407214435666.png)

![image-20260407214454515](assets/image-20260407214454515.png)

## 快速开始

### 环境要求

- Windows 10及以上
- Ubuntu 22.04及以上
- Python 3.12 或更高版本（仅源码环境运行需要）

### 使用方式

#### 方式一：直接使用（推荐）

1. 下载最新版本的可执行文件
2. 双击运行 `YuQue-BdT.exe`
3. 开始使用

#### 方式二：源码运行

1. 克隆或下载本仓库

```bash
git clone https://github.com/Be1k0/YuQue-BdT.git
cd YuQue-BdT
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 运行程序

```bash
python main.py
```

## 自行构建程序

1. 克隆或下载本仓库

```bash
git clone https://github.com/Be1k0/YuQue-BdT.git
cd YuQue-BdT
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 开始构建

```bash
python bulid.py
```


## 更新计划

- [x] 增加适配其他非文档类型的导出功能，如图表、Excel等

- [x] 增加其他公开知识库的导出功能

- [x] 增加UI夜间主题

- [x] 增加支持更多的导出格式，如PDF、Word、JPG、语雀自带格式等

- [x] 增加导出文档里面的图片或视频等文件

- [ ] 增加适配其他空间中的知识库导出

  ...

## 更新日志

### v2.3.0

- 增加markdown格式下导出文档里面的音频或视频等大部分文件的功能
- 增加个人知识库文章导出word与pdf文档格式
- 优化公开知识库导出中全选与取消选择按重叠的问题
- 修复导出文档时进度条会串入其他页面的问题

### v2.2.0

- 软件名字变更为：YuQue-BdT，并替换对应LOGO
- 增加软件内一键更新版本的功能，且启动后自动检测软件当前是否为最新版本
- 增加语雀画板、表格与数据表的导出功能
- 修复部分弹窗显示不完整的问题
- 修复网页登录时语雀验证码一直验证失败的问题
- 修复公开知识库导出时重新混入本地登录 Cookie 导致的权限串扰问题
- 修复多选知识库导出时误复用旧文章选择范围的问题
- 修复多知识库导出场景下文档进度文案分子分母错位的问题
- 修复公开知识库导出空 Markdown 文档时被误判为失败的问题

---

### v2.1.0

- 增加公开知识库按原有文件层级导出
- 增加下载失败项统计
- 增加使用GitHub Actions自动构建可执行文件
- 优化知识库文档类型识别，并将原有的emoji图标替换成svg图标
- 优化拦截非文档的空文件写入
- 优化调试日志记录，屏蔽敏感信息
- 优化图片链接正则提取与写入流程
- 优化设置页面中的单选框样式
- 修复带密码解析时的全局 Cookie 污染问题
- 修复多级文章树复选冲突及进度条文字残留
- 修复搜索文章时出现的报错
- 修复导出因跳过分组标题导致的进度统计丢失问题
- 修复导出键冲突与请求异常问题，统一知识库命名空间解析

---

### v2.0.0

#### 重大变化
- 重构了整个项目，将核心 API 层和 GUI 层分离，使代码更加模块化和易于维护
- GUI 层重构为 MVC 分层架构，提高代码可维护性和可扩展性
- GUI 框架从 PyQt5 升级到 PyQt6，所有 UI 组件 API 随之更新
- 核心 API 层引入异步客户端类，支持异步操作，提高程序性能
- 调度器重构为实例化类，新增信号量并发控制
- 重写了整体GUI布局，界面更加美观和易用
- 异步事件循环从 `nest_asyncio` 迁移到 `qasync`，使用 `QEventLoop` 与 Qt 原生集成，解决事件循环冲突问题
- 解析逻辑从 `yuque.py` 中分离，提取为独立的类，包含知识库 TOC 解析和 URL slug 提取等纯函数

#### 其他改进
- 新增禁用 SSL 证书功能，允许用户禁用 SSL 证书验证，解决部分网络环境下的连接问题
- 新增主题切换功能，支持亮色、暗色两种主题，可以选择自动跟随系统主题
- 新增完整的自定义异常体系，包括基础异常类和具体异常类
- 新增版本更新日志，方便用户了解每次更新的内容
- 新增公开知识库导出功能
- 优化路径管理逻辑，同时兼容 PyInstaller 和 Nuitka 两种打包方式
- 优化错误处理机制，提升程序稳定性
- 优化日志记录和异常处理
- 优化文章层级显示效果
- 图片下载线程由最高30改为最高50

---

### v1.1.0

- 新增语雀网页端登陆功能
- 新增文档层级结构支持，实现文档层级显示和交互功能
- 优化图片下载为独立线程
- 优化页面布局和整体代码结构
- 优化设置的保存功能
- 优化头像加载逻辑
- 优化图片下载前的检查逻辑
- 修复因知识库内有同名文档导致出现文档跳过下载的问题

---

### v1.0.0

- 首次发布
- 支持语雀知识库批量导出
- 图形用户界面
- 图片自动下载
- 多线程并发处理
- 智能缓存机制

## 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进这个项目！

## 许可证

本项目采用 GPL 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

<div align="center">

## 致谢

**感谢每一位为本项目提交 Issue、反馈 Bug、提出优化建议的用户，你们的每一份反馈，都是项目持续迭代、稳定优化的核心动力。**

---

![](https://api.star-history.com/svg?repos=be1k0%2FYuQue-BdT)

如果这个项目对您有帮助，请给个 ⭐ Star 支持一下！

Copyright © 2025-2026 By [Be1k0](https://github.com/Be1k0)