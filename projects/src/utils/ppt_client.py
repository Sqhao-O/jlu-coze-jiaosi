"""Coze Doc Maker 工作流 API 客户端"""

import os
import httpx

COZE_WORKFLOW_URL = "https://nxzmj5grqp.coze.site/run"
COZE_API_TOKEN = os.environ.get("COZE_LOOP_API_TOKEN", "")


async def call_ppt_workflow(
    topic: str,
    subject: str = "",
    grade: str = "",
    duration: int = 45,
    objectives: str = "",
    key_points: str = "",
    difficult_points: str = "",
    style: str = "",
) -> str:
    """调用 Coze PPT 生成工作流，返回 .pptx 下载链接"""
    payload = {
        "topic": topic,
        "subject": subject,
        "grade": grade,
        "duration": duration,
    }
    if objectives:
        payload["objectives"] = objectives
    if key_points:
        payload["key_points"] = key_points
    if difficult_points:
        payload["difficult_points"] = difficult_points
    if style:
        payload["style"] = style

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            COZE_WORKFLOW_URL,
            headers={
                "Authorization": f"Bearer {COZE_API_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        ppt_url = data.get("ppt_url", "")
        if not ppt_url:
            raise ValueError(f"PPT 生成失败: {data}")
        return ppt_url
