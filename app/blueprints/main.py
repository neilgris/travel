from flask import Blueprint, render_template, current_app, send_from_directory, redirect, url_for

from app.services.globe import build_globe_data

bp = Blueprint("main", __name__)


@bp.route("/")
def root():
    # 默认进日常消费——这是日常打开更频繁用到的模块；地球首页挪到 /travel，
    # 顶栏「✈ 旅行记录」入口不受影响（url_for("main.index") 已跟着改指向 /travel）。
    return redirect(url_for("expenses.list"))


@bp.route("/travel")
def index():
    return render_template("home.html", globe=build_globe_data())


@bp.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
