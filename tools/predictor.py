"""價格預測：每物品 × 星期幾中位數 + 全區漲跌修正。

v3.2 改版：捨棄線性外推，改用週循環模型。
- Base: 該物品在「目標星期幾」的歷史價格中位數（只用 2026-04-17 改版後資料）
- Drift: 同 region 全體最近 7 天 vs 全期的相對偏離率（阻尼 0.5），套上 base
- Fallback: 同 weekday 無資料時改用該物品全期中位數，標 data_insufficient
"""
from datetime import date, timedelta
import statistics

# 上次大改版日：早於此日的價格行情不同，預測時排除
PATCH_CUTOFF = '2026-04-17'


def predict_series(series, n_future=7, from_date=None, region_history=None):
    """從歷史推算未來 N 天的每日預測。

    series: list[(game_date_str, price_int)]，該物品歷史
    n_future: 預測天數
    from_date: 起算日（不含），預設今日；'YYYY-MM-DD'
    region_history: dict[item_id -> list[(date, price)]]，同 region 所有物品歷史；
                    用來計算全體 drift。傳 None 時 drift=1.0
    回傳：
        {
            'predictions': [{'date', 'predicted'}, ...],
            'confidence': 0.0~1.0,
            'sample_size': int (該物品歷史總筆數),
            'data_insufficient': bool (任一天觸發 fallback 即 True),
        }
    """
    n_total = len(series)
    result = {'predictions': [], 'confidence': 0.0,
              'sample_size': n_total, 'data_insufficient': False}
    if n_total == 0:
        return result

    post_patch = [(d, p) for d, p in series if d >= PATCH_CUTOFF]
    all_prices = [p for _, p in series]
    item_min = min(all_prices)
    item_max = max(all_prices)
    item_fallback_median = statistics.median(all_prices)

    drift = _calc_region_drift(region_history, from_date)
    drift_adj = 1 + (drift - 1) * 0.5  # 阻尼 0.5

    base = date.fromisoformat(from_date) if from_date else date.today()
    predictions = []
    sample_counts = []
    cv_values = []
    any_fallback = False

    for d_off in range(1, n_future + 1):
        target = base + timedelta(days=d_off)
        target_dow = target.weekday()

        # 取改版後同 weekday 樣本
        weekday_samples = [p for dt, p in post_patch
                           if date.fromisoformat(dt).weekday() == target_dow]

        if weekday_samples:
            base_pred = statistics.median(weekday_samples)
            n = len(weekday_samples)
            if n >= 2:
                cv = statistics.stdev(weekday_samples) / base_pred if base_pred > 0 else 0.5
            else:
                cv = 0.5  # 單筆樣本給保守 CV
        else:
            # Fallback：用該物品全期中位數
            any_fallback = True
            base_pred = item_fallback_median
            n = 0
            cv = 0.5

        sample_counts.append(n)
        cv_values.append(cv)

        adjusted = base_pred * drift_adj
        # 夾範圍防暴衝
        adjusted = max(item_min * 0.8, min(item_max * 1.2, adjusted))
        adjusted = max(adjusted, 1.0)

        predictions.append({
            'date': target.isoformat(),
            'predicted': int(round(adjusted)),
        })

    # 信心度：樣本量分數 0.5 + 變異性分數 0.5
    avg_n = statistics.mean(sample_counts) if sample_counts else 0
    avg_cv = statistics.mean(cv_values) if cv_values else 0.5
    n_score = min(avg_n / 4.0, 1.0)
    cv_score = 1 - min(avg_cv, 0.5) / 0.5
    confidence = round(0.5 * n_score + 0.5 * cv_score, 2)
    if any_fallback:
        confidence = min(confidence, 0.3)

    result['predictions'] = predictions
    result['confidence'] = confidence
    result['data_insufficient'] = any_fallback
    return result


def _calc_region_drift(region_history, from_date):
    """全體 drift：region 內每物品「最近 7 天中位數 / 全期中位數」的平均。

    1.0 = 沒變、1.1 = 整體漲 10%、0.9 = 整體跌 10%
    """
    if not region_history:
        return 1.0

    base = date.fromisoformat(from_date) if from_date else date.today()
    recent_cutoff = (base - timedelta(days=7)).isoformat()

    ratios = []
    for hist in region_history.values():
        post = [(d, p) for d, p in hist if d >= PATCH_CUTOFF]
        recent = [p for d, p in post if d >= recent_cutoff]
        if len(post) >= 3 and len(recent) >= 2:
            overall = statistics.median([p for _, p in post])
            rec_med = statistics.median(recent)
            if overall > 0:
                ratios.append(rec_med / overall)

    if not ratios:
        return 1.0
    return statistics.mean(ratios)


def predict_next_week(series):
    """向後相容：只回傳第 7 天的單一預測值（不帶 region drift）。"""
    result = predict_series(series, n_future=7)
    if not result['predictions']:
        return {'predicted': None,
                'confidence': result['confidence'],
                'sample_size': result['sample_size']}
    return {
        'predicted': result['predictions'][-1]['predicted'],
        'confidence': result['confidence'],
        'sample_size': result['sample_size'],
    }
