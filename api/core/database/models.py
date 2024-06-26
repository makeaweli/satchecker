from datetime import datetime

from core import db
from sqlalchemy import DateTime
from zoneinfo import ZoneInfo


class Satellite(db.Model):
    __tablename__ = "satellites"

    id = db.Column(db.Integer, primary_key=True)
    sat_number = db.Column(db.String())
    sat_name = db.Column(db.String())
    constellation = db.Column(db.String())
    date_added = db.Column(DateTime, default=datetime.now(ZoneInfo("UTC")))
    rcs_size = db.Column(db.String())
    launch_date = db.Column(db.DateTime())
    decay_date = db.Column(db.DateTime())
    object_id = db.Column(db.String())
    object_type = db.Column(db.String())

    def __init__(self, sat_number, sat_name, constellation):
        self.sat_number = sat_number
        self.sat_name = sat_name
        self.constellation = constellation

    def __repr__(self):
        return f"<Satellite {self.sat_name}>"


class TLE(db.Model):
    __tablename__ = "tle"

    id = db.Column(db.Integer, primary_key=True)
    sat_id = db.Column(db.Integer(), db.ForeignKey("satellites.id"))
    date_collected = db.Column(db.DateTime())
    tle_line1 = db.Column(db.String())
    tle_line2 = db.Column(db.String())
    is_supplemental = db.Column(db.Boolean())
    data_source = db.Column(db.String())
    epoch = db.Column(db.DateTime())
    tle_satellite = db.relationship("database.models.Satellite", lazy="joined")

    def __init__(
        self,
        sat_id,
        date_collected,
        tle_line1,
        tle_line2,
        is_supplemental,
        epoch,
        data_source,
    ):
        self.sat_id = sat_id
        self.date_collected = date_collected
        self.tle_line1 = tle_line1
        self.tle_line2 = tle_line2
        self.is_supplemental = is_supplemental
        self.data_source = data_source
        self.epoch = epoch

    def __repr__(self):
        return f"<TLE {self.tle_satellite}>"
