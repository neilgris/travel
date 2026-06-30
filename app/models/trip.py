from app.extensions import db

trip_person = db.Table(
    "trip_person",
    db.Column("trip_id", db.ForeignKey("trip.id"), primary_key=True),
    db.Column("person_id", db.ForeignKey("person.id"), primary_key=True),
)


class Trip(db.Model):
    __tablename__ = "trip"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text)

    legs = db.relationship("Leg", backref="trip", order_by="Leg.seq",
                           cascade="all, delete-orphan")
    currencies = db.relationship("TripCurrency", backref="trip",
                                 cascade="all, delete-orphan")
    # days relationship added in Task 5 when Day model is defined
    people = db.relationship("Person", secondary=trip_person, backref="trips")

    @property
    def cities(self):
        seen, out = set(), []
        for leg in self.legs:
            for c in (leg.from_city, leg.to_city):
                if c and c.id not in seen:
                    seen.add(c.id); out.append(c)
        return out

    @property
    def transport_modes(self):
        out = []
        for leg in self.legs:
            if leg.transport_mode and leg.transport_mode not in out:
                out.append(leg.transport_mode)
        return out


class Leg(db.Model):
    __tablename__ = "leg"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.ForeignKey("trip.id"), nullable=False)
    seq = db.Column(db.Integer, nullable=False, default=1)
    from_city_id = db.Column(db.ForeignKey("city.id"))
    to_city_id = db.Column(db.ForeignKey("city.id"))
    transport_mode = db.Column(db.String(20))

    from_city = db.relationship("City", foreign_keys=[from_city_id])
    to_city = db.relationship("City", foreign_keys=[to_city_id])


class TripCurrency(db.Model):
    __tablename__ = "trip_currency"
    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.ForeignKey("trip.id"), nullable=False)
    currency_code = db.Column(db.String(10), nullable=False)
    rate = db.Column(db.Numeric(12, 4), nullable=False)
