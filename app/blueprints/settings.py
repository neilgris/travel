from flask import (Blueprint, render_template, request, redirect,
                   url_for, current_app, flash, abort)
from app.extensions import db
from app.models.person import Person
from app.models.city import City
from app.models.trip import Leg
from app.models.day import Day
from app.services.geocoding import geocode
from app.services.uploads import save_upload

bp = Blueprint("settings", __name__, url_prefix="/settings")


def _parse_coord(value):
    """把表单里的坐标字符串转成 float，空或非法返回 None。"""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _group_cities_by_country():
    """按国家分组城市，返回 [(国家标题, [城市...])]；无国家的归入「未分类」放最后。"""
    cities = City.query.order_by(City.name).all()
    groups = {}
    for c in cities:
        groups.setdefault(c.country, []).append(c)
    ordered = [(k, groups[k]) for k in sorted(g for g in groups if g)]
    if None in groups:
        ordered.append(("未分类", groups[None]))
    return ordered


@bp.route("/people", methods=["GET", "POST"])
def people():
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("名称不能为空")
            return redirect(url_for("settings.people"))
        photo = save_upload(request.files.get("photo"),
                            current_app.config["UPLOAD_FOLDER"])
        db.session.add(Person(name=name, photo=photo))
        db.session.commit()
        flash("已添加同行人")
        return redirect(url_for("settings.people"))
    return render_template("settings/people.html",
                           people=Person.query.order_by(Person.name).all())


@bp.route("/people/<int:pid>/edit", methods=["POST"])
def edit_person(pid):
    person = db.session.get(Person, pid) or abort(404)
    name = request.form["name"].strip()
    if not name:
        flash("名称不能为空")
        return redirect(url_for("settings.people"))
    person.name = name
    photo = save_upload(request.files.get("photo"),
                        current_app.config["UPLOAD_FOLDER"])
    if photo:
        person.photo = photo
    db.session.commit()
    flash("已更新同行人")
    return redirect(url_for("settings.people"))


@bp.route("/people/<int:pid>/delete", methods=["POST"])
def delete_person(pid):
    person = db.session.get(Person, pid) or abort(404)
    if person.trips:
        flash(f"无法删除：{person.name} 已被 {len(person.trips)} 个旅程使用")
        return redirect(url_for("settings.people"))
    db.session.delete(person)
    db.session.commit()
    flash("已删除同行人")
    return redirect(url_for("settings.people"))


@bp.route("/cities", methods=["GET", "POST"])
def cities():
    if request.method == "POST":
        name = request.form["name"].strip()
        if not name:
            flash("名称不能为空")
            return redirect(url_for("settings.cities"))
        coords = geocode(name)
        lat, lon = coords if coords else (None, None)
        db.session.add(City(name=name, latitude=lat, longitude=lon,
                            country=request.form.get("country") or None))
        db.session.commit()
        flash("已添加城市" + ("" if coords else "（未找到坐标，可稍后补）"))
        return redirect(url_for("settings.cities"))
    return render_template("settings/cities.html",
                           city_groups=_group_cities_by_country())


@bp.route("/cities/<int:cid>/edit", methods=["POST"])
def edit_city(cid):
    city = db.session.get(City, cid) or abort(404)
    name = request.form["name"].strip()
    if not name:
        flash("名称不能为空")
        return redirect(url_for("settings.cities"))
    city.name = name
    city.country = request.form.get("country") or None
    if request.form.get("regeocode"):
        coords = geocode(name)
        city.latitude, city.longitude = coords if coords else (None, None)
        flash("已更新城市" + ("" if coords else "（未找到坐标）"))
    else:
        city.latitude = _parse_coord(request.form.get("latitude"))
        city.longitude = _parse_coord(request.form.get("longitude"))
        flash("已更新城市")
    db.session.commit()
    return redirect(url_for("settings.cities"))


@bp.route("/cities/<int:cid>/delete", methods=["POST"])
def delete_city(cid):
    city = db.session.get(City, cid) or abort(404)
    in_leg = Leg.query.filter(
        (Leg.from_city_id == cid) | (Leg.to_city_id == cid)).count()
    in_day = Day.query.filter_by(city_id=cid).count()
    if in_leg or in_day:
        flash(f"无法删除：{city.name} 已被行程或某天使用")
        return redirect(url_for("settings.cities"))
    db.session.delete(city)
    db.session.commit()
    flash("已删除城市")
    return redirect(url_for("settings.cities"))
