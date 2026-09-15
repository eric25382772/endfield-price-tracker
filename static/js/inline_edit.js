(function () {
    'use strict';

    // 關掉目前開著的編輯框
    function closeActiveEditor() {
        var form = document.querySelector('.inline-edit-form');
        if (!form) return;
        var cell = form.closest('.editable-cell');
        form.remove();
        cell.querySelector('.cell-value').style.display = '';
        cell.querySelector('.edit-btn').style.display = '';
    }

    // 畫出利潤欄的文字（正的綠、負的紅）
    function renderProfit(profit) {
        if (profit === null || profit === undefined) {
            return '<span class="text-muted">-</span>';
        }
        var cls = profit > 0 ? 'text-success' : (profit < 0 ? 'text-danger' : '');
        var prefix = profit > 0 ? '+' : '';
        return '<span class="' + cls + '">' + prefix + profit + '</span>';
    }

    // 同區當日最高利潤：伺服器的必買／可買都拿它當基準，這裡從同一張表的利潤欄重算
    function regionTopProfit(row) {
        var top = 0;
        row.closest('tbody').querySelectorAll('.profit-cell').forEach(function (c) {
            var v = parseInt(c.textContent.replace(/[^\-\d]/g, ''), 10);
            if (!isNaN(v) && v > top) top = v;
        });
        return top;
    }

    // 畫出「建議」欄的徽章（規則對齊 compare.html 的 suggestion_badge；
    // 建議囤貨與別買由伺服器判斷，重新整理後才會更新）
    function renderBadge(profit, row) {
        if (profit === null || profit === undefined) {
            return '<span class="text-muted">-</span>';
        }
        var top = regionTopProfit(row);
        if (profit >= window.PROFIT_THRESHOLD && profit >= top) {
            return '<span class="badge bg-success">必買</span>';
        }
        if (top > 0 && profit >= top * window.BUYABLE_RATIO) {
            return '<span class="badge bg-info">可買</span>';
        }
        if (profit > 0) {
            return '<span class="badge bg-warning text-dark">低利潤</span>';
        }
        if (profit === 0) {
            return '<span class="badge bg-secondary">持平</span>';
        }
        return '<span class="badge bg-danger">虧損</span>';
    }

    // 綠底＝必買／建議囤貨，跟徽章同一份判斷（見 app.py _mark_row_flags）
    function updateRowClass(row, profit) {
        row.classList.remove('table-success', 'table-danger');
        var badgeCell = row.querySelector('.badge-cell');
        if (badgeCell.querySelector('.badge.bg-success, [data-stockpile-pick]')) {
            row.classList.add('table-success');
        } else if (profit !== null && profit !== undefined && profit < 0) {
            row.classList.add('table-danger');
        }
    }

    // 存檔成功後讓格子閃一下
    function flashCell(cell) {
        cell.classList.remove('cell-flash');
        // 強迫瀏覽器重算版面，動畫才會重播
        void cell.offsetWidth;
        cell.classList.add('cell-flash');
    }

    // 打開格子裡的編輯框
    function openEditor(cell) {
        closeActiveEditor();

        var valueSpan = cell.querySelector('.cell-value');
        var editBtn = cell.querySelector('.edit-btn');
        var currentText = valueSpan.textContent.trim();
        var currentVal = currentText === '-' ? '' : currentText;

        valueSpan.style.display = 'none';
        editBtn.style.display = 'none';

        var form = document.createElement('div');
        form.className = 'inline-edit-form d-flex align-items-center justify-content-center gap-1';
        form.innerHTML =
            '<input type="number" class="form-control form-control-sm" min="100" max="8000" placeholder="' + (currentVal || '100-8000') + '">' +
            '<button class="btn btn-sm btn-success confirm-edit" title="確認">&#10003;</button>' +
            '<button class="btn btn-sm btn-outline-secondary cancel-edit" title="取消">&#10007;</button>';
        cell.appendChild(form);

        var input = form.querySelector('input');
        input.focus();
        input.select();
    }

    // 送出修改
    function submitEdit(cell) {
        var input = cell.querySelector('.inline-edit-form input');
        if (input.value.trim() === '') {
            closeActiveEditor();
            return;
        }
        var val = parseInt(input.value, 10);
        if (isNaN(val) || val < 100 || val > 8000) {
            input.classList.add('is-invalid');
            return;
        }

        var type = cell.dataset.type;
        var itemId = parseInt(cell.dataset.itemId, 10);
        var gameDate = cell.dataset.gameDate;
        var url, body;

        if (type === 'my_price') {
            url = '/api/price';
            body = { item_id: itemId, market_price: val, game_date: gameDate };
        } else {
            url = '/api/friend-price';
            var friendName = cell.dataset.friendName || '好友';
            body = { item_id: itemId, market_price: val, friend_name: friendName, game_date: gameDate };
        }

        var confirmBtn = cell.querySelector('.confirm-edit');
        confirmBtn.disabled = true;
        confirmBtn.textContent = '...';

        fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (!data.ok) {
                alert(data.error || '儲存失敗');
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '&#10003;';
                return;
            }

            // 找到這格所在的那一列
            var row = cell.closest('tr');

            // 更新「我的價格」欄
            var myCell = row.querySelector('[data-type="my_price"]');
            var myVal = data.my_price;
            myCell.querySelector('.cell-value').textContent = myVal !== null ? myVal : '-';

            // 更新「好友價格」欄
            var friendCell = row.querySelector('[data-type="friend_price"]');
            var friendVal = data.friend_price;
            friendCell.querySelector('.cell-value').textContent = friendVal !== null ? friendVal : '-';
            if (data.best_friend) {
                friendCell.dataset.friendName = data.best_friend;
            }

            // 更新「好友」欄（第 4 格），要保留它可以點進去改名
            var cells = row.querySelectorAll('td');
            var fnCell = cells[3];
            var rawName = data.best_friend || '';
            fnCell.dataset.rawFriend = rawName;
            fnCell.innerHTML = '<span class="fn-value"><small>' + (data.best_friend || '-') + '</small></span>' +
                (rawName ? ' <button class="btn btn-sm edit-btn fn-edit-btn" title="修正名稱">&#9998;</button>' : '');

            // 更新「利潤」欄
            var profitCell = row.querySelector('.profit-cell');
            profitCell.innerHTML = renderProfit(data.profit);

            // 更新「建議」欄（建議囤貨這裡算不出來，保留伺服器原本掛的那顆）
            var badgeCell = row.querySelector('.badge-cell');
            var stockpileBadge = badgeCell.querySelector('[data-stockpile-pick]');
            badgeCell.innerHTML = renderBadge(data.profit, row);
            if (stockpileBadge) {
                badgeCell.appendChild(document.createElement('br'));
                badgeCell.appendChild(stockpileBadge);
            }

            // 更新整列的底色
            updateRowClass(row, data.profit);

            // 收起編輯框，然後閃一下
            closeActiveEditor();
            flashCell(cell);
        })
        .catch(function () {
            alert('網路錯誤，請重試');
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '&#10003;';
        });
    }

    // 事件統一掛在 document 上，動態產生的按鈕才點得到
    document.addEventListener('click', function (e) {
        // 點了鉛筆圖示
        if (e.target.closest('.edit-btn')) {
            e.preventDefault();
            var cell = e.target.closest('.editable-cell');
            if (cell) openEditor(cell);
            return;
        }

        // 點了打勾
        if (e.target.closest('.confirm-edit')) {
            e.preventDefault();
            var cell = e.target.closest('.editable-cell');
            if (cell) submitEdit(cell);
            return;
        }

        // 點了叉叉
        if (e.target.closest('.cancel-edit')) {
            e.preventDefault();
            closeActiveEditor();
            return;
        }

        // 點編輯框外面就收起來
        if (!e.target.closest('.inline-edit-form') && !e.target.closest('.edit-btn')) {
            closeActiveEditor();
        }
    });

    // 鍵盤：Enter 確認、Esc 取消
    document.addEventListener('keydown', function (e) {
        var form = document.querySelector('.inline-edit-form');
        if (!form) return;

        if (e.key === 'Enter') {
            e.preventDefault();
            var cell = form.closest('.editable-cell');
            if (cell) submitEdit(cell);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            closeActiveEditor();
        }
    });
})();


// ===== 好友名稱手動修正（v4.1）=====
(function () {
    'use strict';

    function closeFnEditor() {
        var form = document.querySelector('.fn-edit-form');
        if (!form) return;
        var cell = form.closest('.friend-name-cell');
        form.remove();
        if (!cell) return;
        var v = cell.querySelector('.fn-value');
        if (v) v.style.display = '';
        var btn = cell.querySelector('.fn-edit-btn');
        if (btn) btn.style.display = '';
    }

    function openFnEditor(cell) {
        closeFnEditor();
        var valueSpan = cell.querySelector('.fn-value');
        var btn = cell.querySelector('.fn-edit-btn');
        var current = valueSpan.textContent.trim();
        if (current === '-') current = '';
        valueSpan.style.display = 'none';
        if (btn) btn.style.display = 'none';

        var form = document.createElement('div');
        form.className = 'fn-edit-form d-flex align-items-center justify-content-center gap-1';
        form.innerHTML =
            '<input type="text" class="form-control form-control-sm" style="max-width:130px" value="' +
            current.replace(/"/g, '&quot;') + '">' +
            '<button class="btn btn-sm btn-success fn-confirm" title="確認">&#10003;</button>' +
            '<button class="btn btn-sm btn-outline-secondary fn-cancel" title="取消">&#10007;</button>';
        cell.appendChild(form);
        var input = form.querySelector('input');
        input.focus();
        input.select();
    }

    function submitFn(cell) {
        if (!cell) return;
        var input = cell.querySelector('.fn-edit-form input');
        var name = input.value.trim();
        var raw = cell.dataset.rawFriend || '';
        if (name === '' || !raw) { closeFnEditor(); return; }

        var btn = cell.querySelector('.fn-confirm');
        btn.disabled = true;
        btn.textContent = '...';
        fetch('/api/friend-name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ raw: raw, name: name })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.ok) {
                alert(data.error || '儲存失敗');
                btn.disabled = false; btn.innerHTML = '&#10003;';
                return;
            }
            // 同步整頁所有相同 raw 名的顯示（同一好友可能出現在多列）
            document.querySelectorAll('.friend-name-cell').forEach(function (c) {
                if (c.dataset.rawFriend === raw) {
                    var v = c.querySelector('.fn-value');
                    if (v) v.innerHTML = '<small>' + data.name + '</small>';
                }
            });
            closeFnEditor();
        })
        .catch(function () {
            alert('網路錯誤，請重試');
            btn.disabled = false; btn.innerHTML = '&#10003;';
        });
    }

    document.addEventListener('click', function (e) {
        if (e.target.closest('.fn-edit-btn')) {
            e.preventDefault();
            e.stopPropagation();
            var cell = e.target.closest('.friend-name-cell');
            if (cell) openFnEditor(cell);
            return;
        }
        if (e.target.closest('.fn-confirm')) {
            e.preventDefault();
            submitFn(e.target.closest('.friend-name-cell'));
            return;
        }
        if (e.target.closest('.fn-cancel')) {
            e.preventDefault();
            closeFnEditor();
            return;
        }
        if (!e.target.closest('.fn-edit-form') && !e.target.closest('.fn-edit-btn')) {
            closeFnEditor();
        }
    });

    document.addEventListener('keydown', function (e) {
        var form = document.querySelector('.fn-edit-form');
        if (!form) return;
        if (e.key === 'Enter') {
            e.preventDefault();
            submitFn(form.closest('.friend-name-cell'));
        } else if (e.key === 'Escape') {
            e.preventDefault();
            closeFnEditor();
        }
    });
})();
