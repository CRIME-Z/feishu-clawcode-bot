"""Flask 路由"""
from flask import Blueprint, request, jsonify
from .handlers import MessageHandler

bp = Blueprint("routes", __name__)
handler = MessageHandler()

@bp.route("/webhook", methods=["POST"])
def webhook():
    """
    飞书 Webhook 接收端点

    验证: 返回 challenge 字段
    消息: 处理消息并回复
    """
    data = request.json

    # Webhook 验证
    challenge = data.get("challenge")
    if challenge:
        return jsonify({"challenge": challenge})

    # 处理事件
    error = handler.handle_event(data)
    if error:
        return jsonify({"code": 1, "msg": error}), 200

    return jsonify({"code": 0})

@bp.route("/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "clawcode_available": handler.clawcode.is_available()
    })

@bp.route("/test", methods=["GET", "POST"])
def test():
    """测试端点"""
    return jsonify({
        "message": "Feishu ClawCode Bot is running!",
        "clawcode_available": handler.clawcode.is_available()
    })
