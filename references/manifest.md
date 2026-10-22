# 资产清单与辅助脚本

`scripts/check_assets.py` 不生成/编辑图片，不修改文件；输出 JSON 到标准输出。需要 Python 3.10+；检查 PNG 时需要 Pillow，解析字幕不需要额外库。优先使用已有运行时，缺包时明确说明，不自动安装。

```powershell
python -X utf8 <skill目录>/scripts/check_assets.py srt <字幕.srt>
python <skill目录>/scripts/check_assets.py check <输出目录>/assets.json
```

`srt` 输出字幕编号、start_ms、end_ms、text、duration_ms。`check` 退出码 0 表示结构通过，1 表示检查失败，2 表示输入/依赖错误；不会证明视觉质量。检查阶段应等所有请求资产登记后执行；中间态失败是预期行为，续做时不要跳过未完成项。

## 原创说明动画

原创说明动画使用 `kind: "broll", subtype: "explainer", media_type: "video"`；人物卡动画使用 `subtype: "profile_card"`。原创版式不标为网络媒体本身，嵌入照片仍逐项记录来源和许可。`path` 指向MP4；`static_path` 保留完整静态PNG；`editable_path` 指向分语义组SVG；`animation_path` 指向时序JSON（记录组名、start、fade、顺序、帧率和时长）。静态版列入同一资产的附属文件或 previous_paths，不重复计为时间轴插入。原有资产id、目标start_ms/end_ms与source_cues不变；视频内部source_in_ms从0起，source_out_ms等于实际片长，不能混用目标口播时钟。

修订后同步更新剪辑表、预览页、来源表中的选用文件；默认不制作压缩包。用户明确要求压缩包时才更新对应包，既有旧包保留。除通用视频检查外，核对出现顺序、每组与相连箭头的关系、最后至少2秒完整展示，以及静态终态与原图一致。

## 真实图片与视频

B-roll新增可选 `subtype`（scientific_media、news_screenshot、post_screenshot、profile_card、explainer等）、`explanation_gain` 和 `fact_sources`（关键事实及对应URL）。`explanation_gain`由语义判断，写不出具体新增理解就不制作。人物卡/解释图可附 `editable_path`；截图记录 `captured_at`、`published_at`、`event_date`（已知时）及完整原图路径。沿用 kind=broll，无需扩充顶层资产种类，继续参与重叠和密度检查。

B-roll 允许原始图片格式，`media_type: "image"`（默认）或 `"video"`。封面/章节仍要求 PNG。真实素材的 `ratio` 填原文件实际比例，`display_ratio: "16:9"` 记录目标画布；用 `placement` 写留边/画中画建议，不为通过检查强制裁切证据图。

网络素材增加 `origin: "web"`、`source_page`、`download_url`（可选）、`license`、`license_url`、`credit_text`、`accessed_at`、`usage_status: "cleared"`。无需署名时 credit_text 写清依据。检查器只验证记录完整性，许可与科学相关性须读源页确认；未知条件不能标 cleared。`prompt_ref` 可指 `素材来源.csv` 中的检索词记录，真实素材不虚构生成提示词。

视频增加实际 `duration_ms`、`source_in_ms`、`source_out_ms`、`playback_speed`（默认 1），同时保留目标 `start_ms/end_ms/source_cues`。ffprobe 通过 PATH 发现，也可用顶层 `ffprobe_path` 指定已有可执行文件；缺失时报告验证失败，不自动安装。脚本核对源区间不越界、按速度换算的时长与目标区间差不超过 100ms。视频需另行查看所选区间；ffprobe 只测媒体信息。

同一视频源文件可被多个稳定资产 ID 引用，设置 `shared_source: true` 时豁免源文件的目标时间前缀命名；每条仍有独立目标和源片时间，时间表导出时按资产 ID 区分。普通文件名继续用目标时间前缀。只在多个视频片段共享源文件时允许重复 path，其他资产仍拒绝重复。

清单使用 UTF-8 JSON，路径相对清单目录。`requested` 列出本次资产类型；仅封面为 `["cover"]`；整套为 `["cover","chapter","broll"]`。明确只要一个封面比例时同步修改 `cover_ratios`，默认两种。

```json
{
  "requested": ["cover"],
  "cover_ratios": ["16:9", "4:3"],
  "assets": [
    {
      "id": "cover-16x9", "kind": "cover", "ratio": "16:9",
      "path": "封面_主题_16x9.png", "status": "approved",
      "width": 1920, "height": 1080,
      "prompt_ref": "提示词.md#封面", "source": "用户主题和人物图",
      "visual_checked": true, "preview_checked": true,
      "revision_count": 0
    },
    {
      "id": "cover-4x3", "kind": "cover", "ratio": "4:3",
      "path": "封面_主题_4x3.png", "status": "planned",
      "prompt_ref": "提示词.md#封面", "source": "用户主题和人物图"
    }
  ]
}
```

时间轴清单另需顶层 `srt_path`；可选 `duration_ms`（至少覆盖最后字幕，未指定时使用最后字幕结束）、`broll_limit`（默认2）；内容密集时按时间轴参考调整并记录 `broll_density_reason`，不为通过检查盲目提高限制。没有 SRT 的文稿方案可记录 `planned`，不能通过最终时间轴验收。

每个章节/B-roll 另有 `start_ms`、`end_ms` 和非空 `source_cues`（字幕编号字符串数组）。章节可附 `title`；`source_cues` 必须存在且至少一条与该图显示区间相交。章节图另需 `editable_path` 指向含 `<text>` 的 SVG；所有可编辑源文件必须实际重新打开验证，脚本只查存在和文本元素。时间轴图片默认 `ratio: "16:9"`，明确其他比例时按实际配置。

状态：`planned → generated → approved`；失败为 `needs_attention`，不计完成，同时记录 `issue` 的具体缺陷和 `revision_count`（本次任务已用的自动修正次数）。续做不能清零次数。`visual_checked` 仅在人工/模型确实查看后设 true，封面另需 `preview_checked`。width/height 填实际读取值；脚本核对 PNG 解码、声明尺寸、比例（默认相对误差不超过 0.5%）、命名、重叠、越界、字幕关联、滑动密度、重复 id/path 和请求完整性。合适的构图、汉字准确性、人物相似度仍靠视觉检查。

续做保留稳定 id；同一资产的新版更新 path，并记录旧版路径到可选 `previous_paths`。清单只列当前选用版本，避免把备选图算成新的时间轴事件。跨视频复用记录独立素材与各段插入点；同一个视频文件的多个插入记录可使用 `shared_source`，PNG/动画附属文件不计新增插入。每次确认内容改变时将受影响项退回 planned，保留已完成的无关项。

## 媒体与最终目录核验

分别测量画布尺寸、编码、实际时长、音轨和透明度，再查看动画过程与终态。透明度读取解码像素的Alpha通道或已验证的透明判定，不把RGB统计误当Alpha；例如图像库的stats可能统计输入而非前面的通道提取结果，须核对实际返回通道/数据。普通全屏PNG应完全不透明，MP4应使用适合剪辑的编码并无音轨。

SVG嵌入过大照片可能触发解析大小限制；在不重绘照片的前提下使用合适尺寸的展示副本，保留原始文件与真实原始尺寸。重新打开SVG确认照片、中文字与路径可用；定制字形若不可直接编辑须如实记录。科学示意核对必要结构、标签与关系，夸张尺度/转角注明“示意”，不能以好看替代正确结构。

正式目录保留成品、必要可编辑源文件与时序、原素材、来源表、时间表和相对链接预览；渲染缓存与临时调试文件留工作区。复制完成后检查每项引用资源及预览相对链接，必要时以哈希确认关键成品复制完整。原片已在用户目录中时不无故重复打包；默认不生成压缩包。
