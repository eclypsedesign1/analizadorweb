(function () {
  'use strict';

  const isResultsPage = window.location.pathname.startsWith('/results/');
  const jobId = isResultsPage ? window.location.pathname.split('/').pop() : null;

  // ── LANDING PAGE ───────────────────────────────────────────────────────────
  const form = document.getElementById('analyzeForm');
  if (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      const btn = document.getElementById('submitBtn');
      const errEl = document.getElementById('formError');
      errEl.classList.add('hidden');

      const urlInput = document.getElementById('url').value.trim();
      if (!urlInput) {
        errEl.textContent = 'Por favor ingresá la URL de tu sitio.';
        errEl.classList.remove('hidden');
        return;
      }

      let url = urlInput;
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
      }

      btn.disabled = true;
      btn.querySelector('.btn-text').textContent = 'Iniciando análisis...';

      try {
        const res = await fetch('/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url,
            name: document.getElementById('name').value.trim() || null,
            email: document.getElementById('email').value.trim() || null,
          }),
        });
        const data = await res.json();
        if (res.status === 429) {
          errEl.textContent = data.detail || 'Límite de análisis alcanzado. Intentá mañana.';
          errEl.classList.remove('hidden');
          btn.disabled = false;
          btn.querySelector('.btn-text').textContent = 'Analizar mi sitio';
          return;
        }
        if (!res.ok) throw new Error(data.detail || 'Error al iniciar el análisis');
        window.location.href = '/results/' + data.job_id;
      } catch (err) {
        errEl.textContent = err.message || 'Error de conexión. Intentá nuevamente.';
        errEl.classList.remove('hidden');
        btn.disabled = false;
        btn.querySelector('.btn-text').textContent = 'Analizar mi sitio';
      }
    });
  }

  // ── RESULTS PAGE ───────────────────────────────────────────────────────────
  if (!isResultsPage || !jobId) return;

  const $ = id => document.getElementById(id);
  const loadingSection = $('loadingSection');
  const resultsSection = $('resultsSection');
  const errorSection = $('errorSection');

  const MODULE_STEPS = ['cms', 'security', 'performance', 'hosting', 'contacts', 'seo', 'compliance', 'pdf'];
  let currentResult = null;

  function setProgress(pct, msg, module) {
    $('progressBar').style.width = pct + '%';
    $('progressPct').textContent = pct + '%';
    if (msg) $('progressMsg').textContent = msg;

    MODULE_STEPS.forEach(m => {
      const el = $('step-' + m);
      if (!el) return;
      if (m === module) { el.classList.add('active'); el.classList.remove('done'); }
      else if (el.classList.contains('active') && m !== module) {
        el.classList.remove('active'); el.classList.add('done');
      }
    });
  }

  function showError(msg) {
    loadingSection.classList.add('hidden');
    resultsSection.classList.add('hidden');
    errorSection.classList.remove('hidden');
    if (msg) $('errorMsg').textContent = msg;
  }

  function scoreColor(score) {
    if (score >= 70) return '#FF3B3B';
    if (score >= 40) return '#FFAA00';
    return '#22C55E';
  }

  function severityClass(s) { return s === 'critical' ? 'critical' : s === 'warning' ? 'warning' : 'info'; }
  function severityLabel(s) { return s === 'critical' ? 'CRÍTICO' : s === 'warning' ? 'ATENCIÓN' : 'INFO'; }

  function buildIssueEl(issue) {
    const div = document.createElement('div');
    div.className = 'issue-item';
    const sc = severityClass(issue.severity);
    div.innerHTML = `
      <span class="issue-badge ${sc}">${severityLabel(issue.severity)}</span>
      <div class="issue-text">
        <div class="issue-msg">${esc(issue.message)}</div>
        ${issue.detail ? `<div class="issue-detail">${esc(issue.detail)}</div>` : ''}
      </div>`;
    return div;
  }

  function esc(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function buildTable(rows) {
    const table = document.createElement('table');
    table.className = 'info-table';
    rows.forEach(([label, val, cls]) => {
      const tr = document.createElement('tr');
      const valCls = cls ? ` class="${cls}"` : '';
      tr.innerHTML = `<td class="label-col">${esc(label)}</td><td${valCls}>${esc(String(val ?? '—'))}</td>`;
      table.appendChild(tr);
    });
    return table;
  }

  function buildTabContent(data) {
    const { cms, security, performance, hosting, contacts, seo, compliance } = data;

    // CMS
    const cmsEl = $('tab-cms');
    if (cms) {
      const rows = [
        ['CMS detectado', cms.cms || 'Desconocido'],
        ['Versión', cms.version || '—'],
        ['Tema activo', cms.theme || '—'],
        ['Plugins detectados', cms.plugins ? cms.plugins.length : 0],
      ];
      cmsEl.appendChild(buildTable(rows));
      if (cms.issues && cms.issues.length) {
        const h = document.createElement('h3');
        h.textContent = 'Problemas'; h.style.cssText = 'margin:16px 0 8px;font-size:14px';
        cmsEl.appendChild(h);
        cms.issues.forEach(i => cmsEl.appendChild(buildIssueEl(i)));
      }
    }

    // Security
    const secEl = $('tab-security');
    if (security) {
      const rows = [
        ['SSL válido', security.ssl_valid ? '✓ Sí' : '✗ No', security.ssl_valid ? 'val-ok' : 'val-err'],
        ['Emisor SSL', security.ssl_issuer || '—'],
        ['Días para vencer', security.ssl_days_left != null ? security.ssl_days_left + ' días' : '—',
          security.ssl_days_left < 30 ? 'val-err' : security.ssl_days_left < 60 ? 'val-warn' : null],
        ['Archivos expuestos', security.exposed_files && security.exposed_files.length ? security.exposed_files.join(', ') : 'Ninguno',
          security.exposed_files && security.exposed_files.length ? 'val-err' : 'val-ok'],
      ];
      const missingH = Object.entries(security.headers || {}).filter(([, v]) => !v).map(([k]) => k);
      rows.push(['Headers faltantes', missingH.length ? missingH.join(', ') : 'Ninguno', missingH.length ? 'val-warn' : 'val-ok']);
      secEl.appendChild(buildTable(rows));
      if (security.issues && security.issues.length) {
        const h = document.createElement('h3');
        h.textContent = 'Problemas'; h.style.cssText = 'margin:16px 0 8px;font-size:14px';
        secEl.appendChild(h);
        security.issues.forEach(i => secEl.appendChild(buildIssueEl(i)));
      }
    }

    // Performance
    const perfEl = $('tab-performance');
    if (performance) {
      const rows = [
        ['Score mobile', performance.mobile_score != null ? performance.mobile_score + '/100' : '—',
          performance.mobile_score < 50 ? 'val-err' : performance.mobile_score < 70 ? 'val-warn' : 'val-ok'],
        ['Score desktop', performance.desktop_score != null ? performance.desktop_score + '/100' : '—'],
        ['LCP', performance.lcp ? performance.lcp + 's' : '—', performance.lcp > 4 ? 'val-err' : performance.lcp > 2.5 ? 'val-warn' : 'val-ok'],
        ['FCP', performance.fcp ? performance.fcp + 's' : '—'],
        ['CLS', performance.cls != null ? performance.cls : '—', performance.cls > 0.25 ? 'val-warn' : null],
        ['TTFB', performance.ttfb ? performance.ttfb + 's' : '—'],
        ['CDN', performance.uses_cdn ? '✓ ' + (performance.cdn_provider || 'Sí') : '✗ No', performance.uses_cdn ? 'val-ok' : 'val-warn'],
      ];
      perfEl.appendChild(buildTable(rows));
      if (performance.issues && performance.issues.length) {
        const h = document.createElement('h3');
        h.textContent = 'Problemas'; h.style.cssText = 'margin:16px 0 8px;font-size:14px';
        perfEl.appendChild(h);
        performance.issues.forEach(i => perfEl.appendChild(buildIssueEl(i)));
      }
    }

    // Hosting
    const hostEl = $('tab-hosting');
    if (hosting) {
      const rows = [
        ['IP del servidor', hosting.ip || '—'],
        ['Proveedor hosting', hosting.provider || '—'],
        ['Ubicación', [hosting.city, hosting.country].filter(Boolean).join(', ') || '—'],
        ['Email (MX)', hosting.mx_provider || '—'],
        ['Dominio registrado', hosting.domain_registered || '—'],
        ['Dominio vence', hosting.domain_expires || '—'],
      ];
      hostEl.appendChild(buildTable(rows));
    }

    // Contacts
    const contEl = $('tab-contacts');
    if (contacts) {
      const rows = [
        ['Emails encontrados', contacts.emails && contacts.emails.length ? contacts.emails.join(', ') : 'No detectado'],
        ['Teléfonos', contacts.phones && contacts.phones.length ? contacts.phones.join(', ') : 'No detectado'],
        ['Responsable', contacts.contact_name || '—'],
      ];
      Object.entries(contacts.social || {}).forEach(([p, url]) => rows.push([p.charAt(0).toUpperCase() + p.slice(1), url]));
      contEl.appendChild(buildTable(rows));
    }

    // SEO
    const seoEl = $('tab-seo');
    if (seo) {
      const checks = [
        ['Meta title', seo.has_meta_title ? '✓ Sí — ' + (seo.meta_title || '') : '✗ No', seo.has_meta_title ? 'val-ok' : 'val-err'],
        ['Longitud title', seo.meta_title_length + ' chars', (seo.meta_title_length < 30 || seo.meta_title_length > 65) && seo.has_meta_title ? 'val-warn' : null],
        ['Meta description', seo.has_meta_description ? '✓ Sí' : '✗ No', seo.has_meta_description ? 'val-ok' : 'val-warn'],
        ['robots.txt', seo.has_robots_txt ? (seo.robots_blocks_google ? '⚠ Bloquea Googlebot' : '✓ OK') : '✗ No existe', seo.robots_blocks_google ? 'val-err' : seo.has_robots_txt ? 'val-ok' : 'val-warn'],
        ['sitemap.xml', seo.has_sitemap ? '✓ Sí' : '✗ No', seo.has_sitemap ? 'val-ok' : 'val-warn'],
        ['H1 tags', seo.h1_count, seo.h1_count === 1 ? 'val-ok' : seo.h1_count === 0 ? 'val-err' : 'val-warn'],
        ['Alt text imágenes', seo.images_total > 0 ? seo.images_with_alt + '/' + seo.images_total : '—'],
        ['Canonical tag', seo.has_canonical ? '✓ Sí' : '✗ No', seo.has_canonical ? 'val-ok' : null],
        ['Schema markup', seo.has_schema ? '✓ ' + seo.schema_types.join(', ') : '✗ No', seo.has_schema ? 'val-ok' : 'val-warn'],
        ['OG tags', seo.og_title ? '✓ Configurados' : '✗ Incompletos', seo.og_title ? 'val-ok' : 'val-warn'],
        ['Twitter card', seo.has_twitter_card ? '✓ Sí' : '✗ No'],
      ];
      seoEl.appendChild(buildTable(checks));
    }

    // Compliance
    const compEl = $('tab-compliance');
    if (compliance) {
      const rows = [
        ['Cookie banner', compliance.has_cookie_banner ? '✓ Sí' : '✗ No detectado', compliance.has_cookie_banner ? 'val-ok' : 'val-warn'],
        ['Política de privacidad', compliance.has_privacy_policy ? '✓ Sí' : '✗ No', compliance.has_privacy_policy ? 'val-ok' : 'val-warn'],
        ['Google Analytics 4', compliance.has_ga4 ? '✓ Instalado' : '✗ No', compliance.has_ga4 ? 'val-ok' : null],
        ['Google Tag Manager', compliance.has_gtm ? '✓ Instalado' : '✗ No', compliance.has_gtm ? 'val-ok' : null],
        ['Meta Pixel', compliance.has_meta_pixel ? '✓ Instalado' : '✗ No', compliance.has_meta_pixel ? 'val-ok' : null],
        ['Hotjar', compliance.has_hotjar ? '✓ Instalado' : '✗ No'],
        ['Microsoft Clarity', compliance.has_clarity ? '✓ Instalado' : '✗ No'],
      ];
      compEl.appendChild(buildTable(rows));
    }
  }

  function renderResults(data) {
    document.title = 'Análisis de ' + (data.domain || '') + ' | Eclypse';
    $('resultDomain').textContent = data.domain || '';
    $('resultDate').textContent = new Date().toLocaleDateString('es-AR', { day: '2-digit', month: 'long', year: 'numeric' });

    const score = data.score || {};
    const scoreEl = $('scoreNumber');
    scoreEl.textContent = score.total ?? '—';
    scoreEl.style.color = scoreColor(score.total || 0);
    $('scoreLabel').textContent = score.label || '';
    $('scoreLabel').style.color = scoreColor(score.total || 0);

    // Breakdown
    const bdEl = $('breakdownSection');
    Object.entries(score.breakdown || {}).forEach(([k, v]) => {
      const item = document.createElement('div');
      item.className = 'breakdown-item';
      item.innerHTML = `<div class="breakdown-label">${esc(k)}</div><div class="breakdown-val">${v}</div>`;
      bdEl.appendChild(item);
    });

    // Issues
    const issuesList = $('topIssuesList');
    (score.top_issues || []).forEach(issue => issuesList.appendChild(buildIssueEl(issue)));

    buildTabContent(data);

    // Download button
    $('downloadBtn').addEventListener('click', () => {
      window.open('/report/' + data.job_id, '_blank');
    });

    // Tabs
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.add('hidden'));
        tab.classList.add('active');
        $('tab-' + tab.dataset.tab).classList.remove('hidden');
      });
    });

    loadingSection.classList.add('hidden');
    resultsSection.classList.remove('hidden');
  }

  // Connect SSE
  function startStream() {
    const evtSource = new EventSource('/stream/' + jobId);

    evtSource.onmessage = function (e) {
      const data = JSON.parse(e.data);
      if (data.error) { evtSource.close(); showError(data.error); return; }
      if (data.done) {
        evtSource.close();
        // Fetch full result
        fetch('/result/' + jobId)
          .then(r => r.json())
          .then(result => {
            currentResult = result;
            if (result.error) { showError(result.error); return; }
            renderResults(result);
          })
          .catch(() => showError('No se pudo cargar el resultado'));
        return;
      }
      setProgress(data.percent || 0, data.message, data.module);
      $('domainLabel').textContent = 'Analizando...';
    };

    evtSource.onerror = function () {
      evtSource.close();
      showError('Se perdió la conexión con el servidor.');
    };
  }

  startStream();
})();
