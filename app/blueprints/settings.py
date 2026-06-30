from flask import (Blueprint, render_template, request, redirect,
                   url_for, current_app, flash)
from app.extensions import db
from app.models.person import Person
from app.models.city import City
from app.services.geocoding import geocode
from app.services.uploads import save_upload

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/people", methods=["GET", "POST"])
def people():
    if request.method == "POST":
        name = request.form["name"].strip()
        photo = save_upload(request.files.get("photo"),
                            current_app.config["UPLOAD_FOLDER"])
        db.session.add(Person(name=name, photo=photo))
        db.session.commit()
        flash("已添加同行人")
        return redirect(url_for("settings.people"))
    return render_template("settings/people.html",
                           people=Person.query.order_by(Person.name).all())


@bp.route("/cities", methods=["GET", "POST"])
def cities():
    if request.method == "POST":
        name = request.form["name"].strip()
        coords = geocode(name)
        lat, lon = coords if coords else (None, None)
        db.session.add(City(name=name, latitude=lat, longitude=lon,
                            country=request.form.get("country") or None))
        db.session.commit()
        flash("已添加城市" + ("" if coords else "（未找到坐标，可稍后补）"))
        return redirect(url_for("settings.cities"))
    return render_template("settings/cities.html",
                           cities=City.query.order_by(City.name).all())
