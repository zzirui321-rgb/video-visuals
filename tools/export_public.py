"""Export an explicit allowlist from a personal installation. Never delete files."""
import argparse
import re
from pathlib import Path

FILES = ["SKILL.md", "agents/openai.yaml", "scripts/check_assets.py",
         "scripts/render_svg_reveal.cjs"] + [f"references/{name}.md" for name in
         ("animation", "cover", "manifest", "sourcing", "styles", "subtitles", "timeline")]
PRIVATE = {"references/account-preferences.md", "references/cover-pdf-notes.md",
           "references/bilibili-cover-guide.md"}
PREFERENCES = """# 项目偏好（可选）

公开版不包含作者个人账号偏好。先读取用户当前要求、项目 `账号视觉约定.md` 和认可的参考图；已有选择直接沿用，没有约定时由本次内容决定。

- 确认目标平台、比例、受众、标题和风格；16:9 与 4:3 是本技能的可覆盖默认值。
- 人物保护区、字体、颜色、对齐与手势遮挡以用户和项目约定为准，不默认允许遮挡手势。
- 人物卡与说明图可采用普通全屏版式；颜色与肖像布局按项目确定。
- 素材优先可靠原始发布页与明确许可，照片与关键事实分别核验。
- 只将本项目确认的约定保存在项目目录，不把个人资料提交到公共技能仓库。
"""


def public_text(relative, text):
    if relative == "SKILL.md":
        text = text.replace("本账号任务先读取 [已确认账号偏好](references/account-preferences.md)，", "先读取 [项目偏好说明](references/account-preferences.md)，")
        text = text.replace("本账号任务采用已确认账号偏好", "采用当前项目已确认的偏好")
    if relative == "references/cover.md":
        text = text.replace("本账号按 [已确认偏好](account-preferences.md) 在实际文字区整体居中", "按 [项目偏好](account-preferences.md) 选择实际文字区的对齐方式")
        text = text.replace("本账号允许粗暗色描边", "描边按项目风格与可读性需要决定")
        text = re.sub(r"新增依据与未采用建议见 \[PDF学习记录\]\(cover-pdf-notes.md\)。", "", text)
        text = re.sub(r"规则依据用户提供的《封面与标题进阶制作指南》，证据与适用边界见 \[案例学习\]\(bilibili-cover-guide.md\)。需要追溯规则或继续学习新案例时读取该文件，不必每次下载案例。", "以下是可调整的设计建议；平台界面与遮挡位置以本次实际预览为准。", text)
    if relative == "references/sourcing.md":
        text = re.sub(r"本账号任务按 \[账号偏好\]\(account-preferences.md\)，.*?无指定时优先作者、机构原站和公共科学档案。", "按项目指定来源或视觉约定检索；无指定时优先作者、机构原站、公共科学档案和有明确许可的 Wikimedia Commons。", text)
    if relative == "references/styles.md":
        text = text.replace("本账号任务另读取 [已确认偏好](account-preferences.md)，其他账号不套用该个人偏好。", "偏好设置见 [项目偏好说明](account-preferences.md)，不套用其他账号的个人约定。")
    if relative == "references/animation.md":
        text = text.replace("本账号读取 [账号偏好](account-preferences.md) 决定背景与布局，其他账号遵从其项目约定与用户要求。", "读取 [项目偏好](account-preferences.md)，遵从当前项目约定与用户要求决定背景与布局。")
    if relative == "references/timeline.md":
        text = text.replace("本账号默认沿用 [账号偏好](account-preferences.md) 的普通全屏卡片，其他账号遵从其项目约定；", "默认使用普通全屏卡片，按 [项目偏好](account-preferences.md) 调整；")
    if "本账号" in text:
        raise ValueError(f"Personal-account wording needs review: {relative}")
    if re.search(r"(?i)(?:[a-z]:[\\/](?:users|documents)|/Users/|/home/|\bgh[pousr]_[A-Za-z0-9]{20,}|\bsk-[A-Za-z0-9]{20,})", text):
        raise ValueError(f"Local path or credential pattern needs review: {relative}")
    return text


def export(source, destination, write=False):
    if source.resolve() == destination.resolve():
        raise ValueError("Source and export directory must differ")
    discovered = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    unexpected = discovered - set(FILES) - PRIVATE
    if unexpected:
        raise ValueError(f"New files need explicit publication review: {sorted(unexpected)}")
    outputs = {name: public_text(name, (source / name).read_text(encoding="utf-8-sig")) for name in FILES}
    outputs["references/account-preferences.md"] = PREFERENCES
    for name, text in outputs.items():
        if name.endswith(".md"):
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in link or link.startswith("#"):
                    continue
                target = (destination / name).parent / link.split("#")[0]
                if target.resolve() not in {(destination / f).resolve() for f in outputs}:
                    raise ValueError(f"Unresolved local link: {name}: {link}")
    changes = []
    for name, text in outputs.items():
        target = destination / name
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            changes.append(name)
    if write:
        for name in changes:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(outputs[name], encoding="utf-8", newline="\n")
    print(f"{'Exported' if write else 'Preview'}: {len(changes)} changes; {len(outputs)} public skill files")
    for name in changes:
        print(name)
    return changes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write", action="store_true", help="Apply export; otherwise preview only")
    args = parser.parse_args()
    export(args.source, args.destination, args.write)
