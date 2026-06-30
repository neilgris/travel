from flask import Blueprint

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/people")
def people():
    return ""
