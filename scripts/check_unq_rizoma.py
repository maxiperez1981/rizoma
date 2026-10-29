from database import SessionLocal
import models
from services import rizoma_service


EMAILS = [
    "demo.unq.01@rizoma.local",
    "demo.unq.03@rizoma.local",
    "demo.unq.16@rizoma.local",
    "demo.unq.25@rizoma.local",
    "demo.unq.43@rizoma.local",
]


db = SessionLocal()
try:
    print("usuarios_demo", db.query(models.User).filter(models.User.email.like("demo.unq.%@rizoma.local")).count())
    print("topics_total", db.query(models.Topic).count())
    print("user_topics_total", db.query(models.UserTopic).count())
    for email in EMAILS:
        u = db.query(models.User).filter_by(email=email).first()
        print("\n###", u.name, "|", email)
        print("ofrece=", ", ".join((u.can_offer or [])[:4]))
        print("busca=", ", ".join((u.wants_to_learn or [])[:3]))
        caminos = rizoma_service.caminos_sugeridos(db, u, 5)
        if not caminos:
            print("sin caminos indirectos")
        for c in caminos[:5]:
            labels = " -> ".join(p["label"] for p in c["camino"])
            print(f"{c['score']}: {labels}")
finally:
    db.close()
