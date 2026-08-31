from app.strategy.base import BaseStrategy, StrategyContext


class Dummy(BaseStrategy):
    name = "dummy"

    def on_start(self, ctx):
        ctx.log("starting")

    def on_tick(self, ctx, last_price):
        pass

    def on_order_filled(self, ctx, trade):
        pass

    def on_order_rejected(self, ctx, order, err):
        pass

    def on_stop(self, ctx):
        pass


def test_lifecycle_callbacks_run():
    calls = []

    class Recorder(BaseStrategy):
        name = "rec"
        def on_start(self, ctx): calls.append("start")
        def on_tick(self, ctx, lp): calls.append(("tick", lp))
        def on_order_filled(self, ctx, t): calls.append(("fill", t))
        def on_order_rejected(self, ctx, o, e): calls.append(("rej", e))
        def on_stop(self, ctx): calls.append("stop")

    r = Recorder()
    ctx = StrategyContext()
    r.on_start(ctx)
    r.on_tick(ctx, 100.0)
    r.on_order_filled(ctx, {"price": 100.5})
    r.on_order_rejected(ctx, None, "boom")
    r.on_stop(ctx)
    assert calls[0] == "start"
    assert calls[-1] == "stop"