(function () {
    'use strict';

    // Close any active inline editor
    function closeActiveEditor() {
        var form = document.querySelector('.inline-edit-form');
        if (!form) return;
        var cell = form.closest('.editable-cell');
        form.remove();
        cell.querySelector('.cell-value').style.display = '';
        cell.querySelector('.edit-btn').style.display = '';
    }

    // Render profit text
    function renderProfit(profit) {
        if (profit === null || profit === undefined) {
            return '<span class="text-muted">-</span>';
        }
        var cls = profit > 0 ? 'text-success' : (profit < 0 ? 'text-danger' : '');
        var prefix = profit > 0 ? '+' : '';
        return '<span class="' + cls + '">' + prefix + profit + '</span>';
    }

    // Render badge
    function renderBadge(profit, myPrice) {
        var html = '';
        if (profit === null || profit === undefined) {
            html = '<span class="text-muted">-</span>';
        } else if (profit >= window.PROFIT_THRESHOLD) {
            html = '<span class="badge bg-success">必買</span>';
        } else if (profit >= 1500) {
            html = '<span class="badge bg-info">可買</span>';
        } else if (profit > 0) {
            html = '<span class="badge bg-warning text-dark">低利潤</span>';
        } else if (profit === 0) {
            html = '<span class="badge bg-secondary">持平</span>';
        } else {
            html = '<span class="badge bg-danger">虧損</span>';
        }
        if (myPrice !== null && myPrice !== undefined && myPrice < window.STOCKPILE_THRESHOLD) {
            html += '<br><span class="badge bg-warning text-dark mt-1">建議囤貨</span>';
        }
        return html;
    }

    // Update row class based on profit
    function updateRowClass(row, profit) {
        row.classList.remove('table-success', 'table-danger');
        if (profit !== null && profit !== undefined) {
            if (profit >= window.PROFIT_THRESHOLD) {
                row.classList.add('table-success');
            } else if (profit < 0) {
                row.classList.add('table-danger');
            }
        }
    }

    // Flash animation on cell
    function flashCell(cell) {
        cell.classList.remove('cell-flash');
        // Force reflow
        void cell.offsetWidth;
        cell.classList.add('cell-flash');
    }

    // Open inline editor
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

    // Submit edit
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

            // Find the row
            var row = cell.closest('tr');

            // Update my_price cell
            var myCell = row.querySelector('[data-type="my_price"]');
            var myVal = data.my_price;
            myCell.querySelector('.cell-value').textContent = myVal !== null ? myVal : '-';

            // Update friend_price cell
            var friendCell = row.querySelector('[data-type="friend_price"]');
            var friendVal = data.friend_price;
            friendCell.querySelector('.cell-value').textContent = friendVal !== null ? friendVal : '-';
            if (data.best_friend) {
                friendCell.dataset.friendName = data.best_friend;
            }

            // Update friend name column (4th td, index 3) — keep it editable
            var cells = row.querySelectorAll('td');
            var fnCell = cells[3];
            var rawName = data.best_friend || '';
            fnCell.dataset.rawFriend = rawName;
            fnCell.innerHTML = '<span class="fn-value"><small>' + (data.best_friend || '-') + '</small></span>' +
                (rawName ? ' <button class="btn btn-sm edit-btn fn-edit-btn" title="修正名稱">&#9998;</button>' : '');

            // Update profit
            var profitCell = row.querySelector('.profit-cell');
            profitCell.innerHTML = renderProfit(data.profit);

            // Update badge
            var badgeCell = row.querySelector('.badge-cell');
            badgeCell.innerHTML = renderBadge(data.profit, data.my_price);

            // Update row highlight
            updateRowClass(row, data.profit);

            // Close editor and flash
            closeActiveEditor();
            flashCell(cell);
        })
        .catch(function () {
            alert('網路錯誤，請重試');
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '&#10003;';
        });
    }

    // Event delegation
    document.addEventListener('click', function (e) {
        // Edit button click
        if (e.target.closest('.edit-btn')) {
            e.preventDefault();
            var cell = e.target.closest('.editable-cell');
            if (cell) openEditor(cell);
            return;
        }

        // Confirm button
        if (e.target.closest('.confirm-edit')) {
            e.preventDefault();
            var cell = e.target.closest('.editable-cell');
            if (cell) submitEdit(cell);
            return;
        }

        // Cancel button
        if (e.target.closest('.cancel-edit')) {
            e.preventDefault();
            closeActiveEditor();
            return;
        }

        // Click outside editor closes it
        if (!e.target.closest('.inline-edit-form') && !e.target.closest('.edit-btn')) {
            closeActiveEditor();
        }
    });

    // Keyboard: Enter to confirm, Escape to cancel
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
