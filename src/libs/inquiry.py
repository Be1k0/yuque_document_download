import sys
from typing import List

from .log import Log

try:
    from prompt_toolkit.application.current import get_app
    from InquirerPy import inquirer
    from InquirerPy.base.control import Choice
    from InquirerPy.separator import Separator
except ImportError:
    Log.error("请安装 InquirerPy: pip install InquirerPy")
    sys.exit(1)

from .constants import MutualAnswer, YuqueAccount
from .log import Log
from .tools import get_cache_books_info


def is_running_in_asyncio_loop():
    """检查是否在asyncio事件循环中运行"""
    try:
        return get_app().is_running
    except:
        return False


def ask_user_toc_options() -> MutualAnswer:
    """询问用户导出知识库的选项"""
    answer = MutualAnswer(
        toc_range=[],
        skip=True,
        line_break=True,
        download_range="all"
    )

    try:
        books_info = get_cache_books_info()
        if not books_info:
            Log.error("知识库文件读取失败，程序退出")
            sys.exit(1)

        # 构建选项列表
        options = []
        book_names = []  # 存储所有知识库名称（不含前缀）

        # 首先添加全选选项
        options.append("全选所有知识库")
        options.append(Separator())

        for item in books_info:
            # 区分个人知识库还是团队知识库/协作知识库
            if hasattr(item, 'book_type') and item.book_type == "owner":
                options.append(f"👤 {item.name}")
            else:
                options.append(f"👥 {item.name}")
            book_names.append(item.name)

        # 选择知识库
        if is_running_in_asyncio_loop():
            # 如果在事件循环中，使用同步方式
            import questionary
            selected_books = questionary.checkbox(
                "请选择知识库",
                choices=options
            ).ask()
        else:
            selected_books = inquirer.checkbox(
                message="请选择知识库",
                choices=options,
                instruction="空格选中/取消选中，↑↓键移动选择，全选选项可选择全部知识库"
            ).execute()

        if not selected_books:
            Log.error("未选择知识库，程序退出")
            sys.exit(1)

        # 处理选择结果
        processed_selections = []
        for selection in selected_books:
            # 如果选择了全选选项
            if selection == "✅ 全选所有知识库":
                # 返回所有知识库名称
                processed_selections = book_names
                break
            else:
                # 移除表情符号前缀
                processed_selections.append(selection[2:].strip())

        answer.toc_range = processed_selections

        # 确认是否跳过本地文件
        if is_running_in_asyncio_loop():
            answer.skip = questionary.confirm(
                "是否跳过本地文件?",
                default=True
            ).ask()
        else:
            answer.skip = inquirer.confirm(
                message="是否跳过本地文件?",
                default=True
            ).execute()

        # 确认是否保留语雀换行标识
        if is_running_in_asyncio_loop():
            answer.line_break = questionary.confirm(
                "是否保留语雀换行标识?",
                default=True
            ).ask()
        else:
            answer.line_break = inquirer.confirm(
                message="是否保留语雀换行标识?",
                default=True,
                instruction="</br>在不同平台处理逻辑存在差异，可按需选择是否保留"
            ).execute()

        # 询问下载范围
        range_choices = [
            "下载全部文章",
            "仅下载最近更新的文章",
            "仅下载前N篇文章",
            "选择特定文章下载"
        ]

        if is_running_in_asyncio_loop():
            range_choice = questionary.select(
                "请选择下载范围:",
                choices=range_choices,
                default="下载全部文章"
            ).ask()
        else:
            range_choice = inquirer.select(
                message="请选择下载范围:",
                choices=range_choices,
                default="下载全部文章"
            ).execute()

        # 设置下载范围
        if range_choice == "下载全部文章":
            answer.download_range = "all"
        elif range_choice == "仅下载最近更新的文章":
            answer.download_range = "recent"

            # 询问文章数量
            if is_running_in_asyncio_loop():
                count_str = questionary.text(
                    "请输入文章数量:",
                    default="10"
                ).ask()
            else:
                count_str = inquirer.text(
                    message="请输入文章数量:",
                    default="10",
                    validate=lambda x: x.isdigit() or "请输入有效数字"
                ).execute()

            try:
                from ..libs.constants import GLOBAL_CONFIG
                GLOBAL_CONFIG.article_limit = int(count_str)
            except ValueError:
                GLOBAL_CONFIG.article_limit = 10

        elif range_choice == "仅下载前N篇文章":
            answer.download_range = "custom"

            # 询问文章数量
            if is_running_in_asyncio_loop():
                count_str = questionary.text(
                    "请输入文章数量:",
                    default="10"
                ).ask()
            else:
                count_str = inquirer.text(
                    message="请输入文章数量:",
                    default="10",
                    validate=lambda x: x.isdigit() or "请输入有效数字"
                ).execute()

            try:
                from ..libs.constants import GLOBAL_CONFIG
                GLOBAL_CONFIG.article_limit = int(count_str)
            except ValueError:
                GLOBAL_CONFIG.article_limit = 10
        elif range_choice == "选择特定文章下载":
            answer.download_range = "selected"
            Log.info("选择特定文章下载功能将默认下载所有文章")
            # 特定文章选择功能可以在后续版本中添加

    except KeyboardInterrupt:
        Log.error("用户取消操作，程序退出")
        sys.exit(1)
    except Exception as e:
        Log.error(f"选择出错：{str(e)}，程序退出")
        sys.exit(1)

    return answer


def ask_user_account() -> YuqueAccount:
    """交互式登录"""
    account = YuqueAccount(username="", password="")

    try:
        # 询问用户名
        if is_running_in_asyncio_loop():
            import questionary
            account.username = questionary.text(
                "请输入语雀账号:",
                validate=lambda x: len(x.strip()) > 0
            ).ask()
        else:
            account.username = inquirer.text(
                message="请输入语雀账号:",
                validate=lambda x: len(x.strip()) > 0 or "用户名不能为空"
            ).execute()

        # 询问密码
        if is_running_in_asyncio_loop():
            account.password = questionary.password(
                "请输入语雀密码:",
                validate=lambda x: len(x.strip()) > 0
            ).ask()
        else:
            account.password = inquirer.secret(
                message="请输入语雀密码:",
                validate=lambda x: len(x.strip()) > 0 or "密码不能为空"
            ).execute()

    except KeyboardInterrupt:
        Log.error("用户取消操作，程序退出")
        sys.exit(1)
    except Exception as e:
        Log.error(f"输入出错：{str(e)}，程序退出")
        sys.exit(1)

    return account


def ask_user_choice(message: str, choices: List[str], default: str = None) -> str:
    """询问用户选择"""
    try:
        if is_running_in_asyncio_loop():
            import questionary
            return questionary.select(
                message,
                choices=choices,
                default=default
            ).ask()
        else:
            return inquirer.select(
                message=message,
                choices=choices,
                default=default
            ).execute()
    except KeyboardInterrupt:
        Log.error("用户取消操作，程序退出")
        sys.exit(1)
    except Exception as e:
        Log.error(f"选择出错：{str(e)}，程序退出")
        sys.exit(1)


def ask_user_confirm(message: str, default: bool = True) -> bool:
    """询问用户确认"""
    try:
        if is_running_in_asyncio_loop():
            import questionary
            return questionary.confirm(
                message,
                default=default
            ).ask()
        else:
            return inquirer.confirm(
                message=message,
                default=default
            ).execute()
    except KeyboardInterrupt:
        Log.error("用户取消操作，程序退出")
        sys.exit(1)
    except Exception as e:
        Log.error(f"确认出错：{str(e)}，程序退出")
        sys.exit(1)


def ask_user_input(message: str, default: str = "", validate_func=None) -> str:
    """询问用户输入"""
    try:
        if is_running_in_asyncio_loop():
            import questionary
            return questionary.text(
                message,
                default=default,
                validate=validate_func
            ).ask()
        else:
            return inquirer.text(
                message=message,
                default=default,
                validate=validate_func
            ).execute()
    except KeyboardInterrupt:
        Log.error("用户取消操作，程序退出")
        sys.exit(1)
    except Exception as e:
        Log.error(f"输入出错：{str(e)}，程序退出")
        sys.exit(1)
