from __future__ import annotations

import re

import httpx

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

DOMAIN = "https://18comic.ink"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


async def search_jm(keyword: str, limit: int = 3) -> list[dict]:
    """在禁漫天堂搜索关键词，返回 [{id, url}]。"""
    url = f"{DOMAIN}/search/photos"
    params = {"search_query": keyword, "main_tag": "0"}
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers={"User-Agent": UA})
    html = resp.text
    ids: list[str] = []
    for raw in re.findall(r"/album/(\d+)", html):
        if int(raw) > 1000 and raw not in ids:
            ids.append(raw)
    return [{"id": i, "url": f"{DOMAIN}/album/{i}"} for i in ids[:limit]]


@register("jm_lookup", "dsh", "按关键词查禁漫天堂编号", "0.1.0")
class JmLookupPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("jm")
    async def jm_cmd(self, event: AstrMessageEvent, keyword: str = ""):
        """用法：/jm <关键词>"""
        kw = keyword.strip()
        if not kw:
            yield event.plain_result("用法：/jm 关键词（本子名/作者名）")
            return
        try:
            hits = await search_jm(kw)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"jm_lookup search failed: {exc}")
            yield event.plain_result(f"查不到，站点抽风了：{exc}")
            return
        if not hits:
            yield event.plain_result(f"「{kw}」没搜到东西，换个词试试")
            return
        lines = [f"「{kw}」搜到这些："]
        for h in hits:
            lines.append(f"JM{h['id']}  {h['url']}")
        yield event.plain_result("\n".join(lines))

    @filter.llm_tool(name="jm_search")
    async def jm_search(self, event: AstrMessageEvent, keyword: str):
        """在禁漫天堂按关键词搜索本子，返回 JM 编号和链接。
        当有人问某本漫画/本子的 JM 编号、或者让你去禁漫找某作品时调用。

        Args:
            keyword(string): 搜索关键词，通常是本子标题、作者名或角色名
        """
        try:
            hits = await search_jm(keyword)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"jm_lookup tool failed: {exc}")
            yield event.plain_result(f"查不到，站点抽风了：{exc}")
            return
        if not hits:
            yield event.plain_result(f"「{keyword}」没搜到，换个词")
            return
        body = "\n".join(f"JM{h['id']}  {h['url']}" for h in hits)
        yield event.plain_result(f"「{keyword}」搜到：\n{body}")
