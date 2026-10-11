"""Phase B seed (spec §7): a lot per drug, one under min_stock, one expiring in 10 days, one expired."""

from app.models import StockLot, StockMovement
from app.seed import seed
from app.services.pharmacy import stock as S
from app.services.schedule import today_local


def test_seed_stock(db):
    seed(db)
    view = {r["drug_id"]: r for r in S.stock_view(db, today_local())}
    assert len(view) == 51 and all(r["lots"] for r in view.values())
    assert (view["d-0001"]["on_hand"], view["d-0001"]["min_stock"], view["d-0001"]["low"]) == (200, 200, False)
    assert view["d-0014"]["low"] is True
    assert view["d-0032"]["expiring"] is True and view["d-0018"]["expired"] is True
    assert [r["drug_id"] for r in S.reorder(db, today_local())] == ["d-0014"]
    assert db.query(StockMovement).filter_by(reason="receipt").count() == db.query(StockLot).count() == 53


def test_seed_stock_is_idempotent(db):
    seed(db)
    seed(db)
    assert db.query(StockLot).count() == 53
