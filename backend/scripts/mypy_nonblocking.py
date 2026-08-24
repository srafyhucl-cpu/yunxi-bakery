"""mypy 渐进式类型检查——非阻断模式。

运行 mypy 检查项目类型，始终返回 0 退出码，
让类型问题作为提示而非阻断提交。
"""

import subprocess
import sys


def main() -> int:
    subprocess.run(
        ["mypy", "--config-file=mypy.ini", "app/"],
        capture_output=False,  # 实时输出到终端
    )
    # 始终返回 0，不阻断提交
    return 0


if __name__ == "__main__":
    sys.exit(main())
