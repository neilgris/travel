from flask import Blueprint

bp = Blueprint("trips", __name__, url_prefix="/trips")


@bp.route("/")
def list():
    return ""


@bp.route("/create")
def create():
    return ""
