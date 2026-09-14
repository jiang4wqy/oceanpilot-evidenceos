/* Confirm a synthetic source event and resume the same request after uncertainty. */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  let dialog;
  async function open({api, templateId, merchantId, actorId}) {
    if (dialog?.open) return;
    const reference = await api(`/case-library/${encodeURIComponent(templateId)}`);
    const template = reference.template?.template || {};
    const originalScheme = String(template.scheme || reference.reference.scheme).toUpperCase().replace(/^MC$/, 'MASTERCARD');
    const scheme = ['VISA','MASTERCARD','AMEX','DISCOVER'].includes(originalScheme) ? originalScheme : 'OTHER';
    const reasons = String(template.reason_code || reference.reference.reason_code).match(/\b(?:\d{2}\.\d+|\d{4}|[A-Z]\d{2})\b/g) || ['SIMULATION'];
    const key = `oceanpilot.simulation.${actorId}`;
    let pending = null, preview = null, busy = false;
    try { pending = JSON.parse(sessionStorage.getItem(key) || 'null'); } catch {}
    dialog = document.createElement('dialog'); dialog.className = 'intake-event-dialog';
    dialog.setAttribute('aria-label', '模拟上游拒付');
    dialog.innerHTML = `<form><div class="dialog-heading"><h2>用此案例模拟拒付</h2><button type="button" class="icon-button" data-close aria-label="关闭">×</button></div><p>${esc(reference.reference.title)} · 合成演练</p><div class="dialog-fields"><label>对应商户<input name="merchant_id" required maxlength="100" value="${esc(merchantId || '')}"></label><label>卡组织<select name="scheme"><option value="VISA">Visa</option><option value="MASTERCARD">Mastercard</option><option value="AMEX">Amex</option><option value="DISCOVER">Discover</option><option value="OTHER">专项合成演练（非银行接入）</option></select></label><label>原因码<input name="reason_code" required maxlength="100" value="${esc(reasons[0] || 'SIMULATION')}"></label><label>争议金额（最小货币单位，如 299 美元填 29900）<input name="amount_minor" type="number" min="1" max="1000000000000" step="1" required></label><label>币种<input name="currency" value="USD" pattern="[A-Z]{3}" maxlength="3" required></label></div><p>系统将为本次演练新建交易和事件，不带入案例中的证据、商户决定或结果。</p><div data-preview></div><div class="notice" data-notice hidden></div><div class="dialog-footer"><button type="button" class="button secondary" data-close>取消</button><button type="submit" class="button primary">预览事件与规则</button></div></form>`;
    document.body.append(dialog);
    const form = dialog.querySelector('form'), notice = dialog.querySelector('[data-notice]'), content = dialog.querySelector('[data-preview]'), submit = form.querySelector('[type=submit]');
    form.elements.scheme.value = scheme;
    const show = text => { notice.textContent = text; notice.hidden = false; };
    const freeze = value => form.querySelectorAll('.dialog-fields input,.dialog-fields select').forEach(x=>x.disabled=value);
    function renderPreview(p) {
      if (p.requires_rule_confirmation) {
        content.innerHTML = `<h3>确认创建演练案件</h3><p>${esc(p.reference.title)}</p><p>商户 ${esc(p.input.merchant_id)} · ${esc(p.input.currency)} ${esc(p.input.amount_minor)} 最小货币单位 · ${esc(p.input.scheme)} ${esc(p.input.reason_code)}</p><p>本案例尚无可直接采用的演练规则。建案后由运营确认可选决定、材料要求和期限，再发布商户待办。</p>${!p.scope_matches ? '<p>本次输入与来源范围不同，仅作为独立衍生演练，不继承原例规则。</p>' : ''}<label class="confirmation"><input type="checkbox" name="confirm_simulation" required>我确认这是独立合成事件，先建案并转交规则核对。</label>`;
      } else {
      content.innerHTML = `<h3>请核对本次演练</h3><p>商户 ${esc(p.input.merchant_id)} · ${esc(p.input.currency)} ${esc(p.input.amount_minor)} 最小货币单位 · ${esc(p.input.scheme)} ${esc(p.input.reason_code)}</p><p>仅采用合成演练规则，不是银行或卡组织正式期限。</p><ul>${p.materials.map(x=>`<li>${esc(x.label)}</li>`).join('')}</ul><p>商户截止：${esc(new Date(p.rule.deadlines.merchant).toLocaleString())}<br>内部处理截止：${esc(new Date(p.rule.deadlines.internal).toLocaleString())}<br>外部截止：${esc(new Date(p.rule.deadlines.external).toLocaleString())}</p><label class="confirmation"><input type="checkbox" name="confirm_simulation" required>我确认上述合成交易、演练规则与期限，并发布商户选择任务。</label>`;
      }

      submit.textContent = p.requires_rule_confirmation ? '确认建案，继续核对规则' : '确认接收并发布商户待办'; freeze(true);
    }
    if (pending) {
      show('有一笔结果待确认的演练请求。重试将使用原请求，不会新建重复案件。');
      content.innerHTML = `<p>原请求：${esc(pending.input.case_template_id)} · ${esc(pending.input.merchant_id)} · ${esc(pending.input.currency)} ${esc(pending.input.amount_minor)} 最小货币单位</p>`;
      freeze(true); submit.textContent = '核对并继续原请求';
    }
    form.addEventListener('submit', async event => {
      event.preventDefault(); if (busy || !form.reportValidity()) return;
      busy = true; submit.disabled = true;
      try {
        if (!preview && !pending) {
          const input = {case_template_id:templateId, merchant_id:form.elements.merchant_id.value.trim(), scheme:form.elements.scheme.value, reason_code:form.elements.reason_code.value, amount_minor:Number(form.elements.amount_minor.value), currency:form.elements.currency.value, received_at:new Date().toISOString()};
          preview = await api('/intake/simulations/preview', {method:'POST',body:JSON.stringify(input)});
          renderPreview(preview); notice.hidden=true;
        } else {
          if (!pending) {
            pending = {input:preview.input, confirmation_token:preview.confirmation_token, confirmed:true, request_id:crypto.randomUUID()};
            sessionStorage.setItem(key, JSON.stringify(pending));
          }
          const result = await api('/intake/simulations', {method:'POST',body:JSON.stringify(pending)});
          if (!['READY','NEEDS_RULE_CONFIRMATION'].includes(result.simulation_status)) {
            show('事件已留存，需运营核对：' + (result.event?.reason || result.simulation_status));
            submit.textContent='再次核对原请求'; return;
          }
          sessionStorage.removeItem(key);
          location.assign(`/v2/operations/cases/${encodeURIComponent(result.case_id)}`);
        }
      } catch (error) {
        show((pending ? '结果尚未确认，可用原请求重试。' : '') + error.message);
      } finally { busy=false; submit.disabled=false; }
    });
    dialog.querySelectorAll('[data-close]').forEach(x=>x.addEventListener('click',()=>{if(!busy){dialog.close();dialog.remove();}}));
    dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();});
    dialog.showModal();
  }
  globalThis.OceanSimulation = {open};
})();
