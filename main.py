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
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}


def _pretty(slug: str) -> str:
    s = slug.replace("-", " ").strip()
    return s[:60] if s else ""


def _parse_albums(html: str, limit: int = 5) -> list[dict]:
    """从 HTML 里提取 /album/<id>/<slug>，按出现顺序去重。"""
    out: list[dict] = []
    seen: set[str] = set()
    for m in re.finditer(r'/album/(\d+)(?:/([a-z0-9\-]+))?', html):
        aid, slug = m.group(1), m.group(2) or ""
        if int(aid) < 1000 or aid in seen:
            continue
        seen.add(aid)
        out.append(
            {
                "id": aid,
                "title": _pretty(slug),
                "url": f"{DOMAIN}/album/{aid}",
            }
        )
        if len(out) >= limit:
            break
    return out


async def _fetch(path: str, params: dict | None = None) -> str:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(DOMAIN + path, params=params, headers=HEADERS)
        resp.raise_for_status()
        return resp.text


async def search_jm(keyword: str, limit: int = 3) -> list[dict]:
    html = await _fetch("/search/photos", {"search_query": keyword, "main_tag": "0"})
    return _parse_albums(html, limit)


async def hot_jm(limit: int = 5) -> list[dict]:
    html = await _fetch("/")
    return _parse_albums(html, limit)


def _fmt(title: str, hits: list[dict]) -> str:
    lines = [f"{title}："]
    for h in hits:
        name = f"  {h['title']}" if h["title"] else ""
        lines.append(f"JM{h['id']}{name}\n{h['url']}")
    return "\n".join(lines)


@register("jm_lookup", "dsh", "按关键词查禁漫天堂编号", "0.2.0")
class JmLookupPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("jm")
    async def jm_cmd(self, event: AstrMessageEvent, keyword: str = ""):
        """用法：/jm <关键词>"""
        kw = keyword.strip()
        if not kw:
            yield event.plain_result("用法：/jm 关键词（本子名/作者名）；看最新的用 /jmhot")
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
        yield event.plain_result(_fmt(f"「{kw}」搜到", hits))

    @filter.command("jmhot")
    async def jm_hot_cmd(self, event: AstrMessageEvent):
        """用法：/jmhot 看最新上架"""
        try:
            hits = await hot_jm()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"jm_lookup hot failed: {exc}")
            yield event.plain_result(f"拿不到列表：{exc}")
            return
        yield event.plain_result(_fmt("最新上架", hits))

    @filter.llm_tool(name="jm_search")
    async def jm_search(self, event: AstrMessageEvent, keyword: str):
        """在禁漫天堂按关键词搜索本子，返回 JM 编号和链接。
        有人问某本漫画/本子的 JM 编号、或者让你去禁漫找某个作品时调用。

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
        yield event.plain_result(_fmt(f"「{keyword}」搜到", hits))

    @filter.llm_tool(name="jm_hot")
    async def jm_hot(self, event: AstrMessageEvent):
        """获取禁漫天堂当前最新上架/热门的本子列表（含 JM 编号）。
        有人要「最新的」「最近热门的」「最近有啥好看的」时调用。
        """
        try:
            hits = await hot_jm()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"jm_lookup hot tool failed: {exc}")
            yield event.plain_result(f"拿不到列表：{exc}")
            return
        yield event.plain_result(_fmt("最新上架", hits))
