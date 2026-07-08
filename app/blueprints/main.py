from flask import Blueprint, render_template, current_app, send_from_directory

from app.services.globe import build_globe_data

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return render_template("home.html", globe=build_globe_data())


@bp.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
