from . import db
from datetime import date

class Forecast(db.Model):
    __tablename__ = "forecasts"
    id = db.Column(db.Integer, primary_key=True)
    sign = db.Column(db.String(20), index=True)
    day = db.Column(db.Date, index=True, default=date.today)
    text = db.Column(db.Text)
    model_version = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=db.func.now())

    __table_args__ = (db.UniqueConstraint("sign", "day", name="uix_sign_day"),)

    def to_dict(self):
        return {
            "id": self.id,
            "sign": self.sign,
            "day": self.day.isoformat(),
            "text": self.text,
            "model_version": self.model_version,
        }
