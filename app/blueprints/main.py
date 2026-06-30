from flask import Blueprint, redirect, url_for, current_app, send_from_directory

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    return redirect(url_for("trips.list"))


@bp.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
