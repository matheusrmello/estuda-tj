'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const state = { questions: [], attempts: [], documents: [], jobs: [], settings: null, currentQuestion: 0, subject: '' };

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function notice(message, error = false) {
  const area = $('#notice');
  area.replaceChildren();
  if (message) area.append(element('p', message, error ? 'error' : 'success'));
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  let result;
  try { result = await response.json(); } catch { throw new Error('Resposta inesperada do servidor.'); }
  if (!response.ok) throw new Error(result.error || `Erro ${response.status}`);
  return result;
}
function showView(name) {
  for (const view of document.querySelectorAll('.view')) view.hidden = view.id !== name;
  for (const nav of document.querySelectorAll('.nav')) {
    const active = nav.dataset.view === name;
    nav.classList.toggle('active', active);
    if (active) nav.setAttribute('aria-current', 'page'); else nav.removeAttribute('aria-current');
  }
  notice('');
  if (name === 'questions') renderQuestion();
  if (name === 'simulations') loadSimulations().catch(error => notice(error.message, true));
  if (name === 'imports') { renderImports(); loadCatalog(); }
  if (name === 'settings') loadSettings().catch(error => notice(`Não foi possível carregar as configurações: ${error.message}`, true));
}
function renderDashboard() {
  $('#metric-questions').textContent = String(state.questions.length);
  $('#metric-attempts').textContent = String(state.attempts.length);
  const graded = state.attempts.filter(a => a.correct === true || a.correct === false || a.correct === 1 || a.correct === 0);
  const correct = graded.filter(a => a.correct === true || a.correct === 1).length;
  const accuracy = graded.length ? Math.round(correct * 100 / graded.length) : null;
  $('#metric-accuracy').textContent = accuracy === null ? '—' : `${accuracy}%`;
  $('#dashboard-summary').textContent = accuracy === null ? 'O aproveitamento aparecerá após respostas com gabarito.' : `${correct} acertos em ${graded.length} tentativas com gabarito.`;
  const goal = state.settings?.daily_goal;
  const now = new Date();
  const today = state.attempts.filter(attempt => { const when = new Date(attempt.created_at); return !Number.isNaN(when.getTime()) && when.getFullYear() === now.getFullYear() && when.getMonth() === now.getMonth() && when.getDate() === now.getDate(); }).length;
  $('#daily-summary').textContent = goal === undefined ? 'Meta indisponível.' : goal === 0 ? `${today} respostas hoje. Meta diária desativada.` : `${today} de ${goal} respostas hoje.`;
}
async function loadSettings() {
  const settings = await api('/api/settings'); state.settings = settings;
  $('#ai-provider').value = settings.ai_provider;
  $('#deepseek-model').value = settings.deepseek_model || '';
  $('#daily-goal').value = String(settings.daily_goal);
  $('#deepseek-key').value = '';
  $('#clear-deepseek-key').checked = false;
  $('#key-state').textContent = `${settings.deepseek_key_configured ? 'Chave configurada para a sessão atual.' : 'Nenhuma chave configurada.'} A chave fica apenas na memória do servidor e não é exibida. Reiniciar o servidor apaga a chave; deixe em branco para mantê-la nesta sessão.`;
  renderDashboard();
}
$('#settings-form').addEventListener('submit', async event => {
  event.preventDefault();
  const save = event.currentTarget.querySelector('button[type=submit]');
  const key = $('#deepseek-key').value.trim(); const clear = $('#clear-deepseek-key').checked;
  if (key && clear) { notice('Informe uma nova chave ou selecione a remoção, não as duas opções.', true); return; }
  const payload = {ai_provider: $('#ai-provider').value, deepseek_model: $('#deepseek-model').value.trim(), daily_goal: Number($('#daily-goal').value)};
  if (key) payload.deepseek_api_key = key;
  if (clear) payload.clear_deepseek_api_key = true;
  save.disabled = true;
  try {
    const settings = await api('/api/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    state.settings = settings; $('#deepseek-key').value = ''; $('#clear-deepseek-key').checked = false;
    await loadSettings(); notice('Configurações salvas.');
  } catch (error) { notice(error.message, true); } finally { save.disabled = false; }
});
function pageNeedsOcr(page) {
  return ['nao_solicitado', 'configuracao_ausente', 'modelo_proibido', 'indisponivel', 'falhou', 'limite_excedido'].includes(page.ocr_status) || (!page.ocr_status && String(page.text || '').replace(/\s/g, '').length < 40);
}
function pageExtractionDescription(page) {
  if (!page) return 'Página indisponível para revisão.';
  const status = page.ocr_status;
  if (status === 'concluido') return 'Texto obtido por OCR. Confira cuidadosamente a página original; o reconhecimento pode conter erros.';
  if (status === 'sem_texto') return 'O OCR não identificou texto nesta página. Confira o PDF original e cadastre as questões manualmente, se necessário.';
  if (status === 'nao_solicitado') return 'OCR não solicitado para esta página. Confira o PDF original ou importe novamente com OCR habilitado.';
  if (status === 'configuracao_ausente') return 'OCR não configurado no servidor. Confira o PDF original e configure o acesso à OpenAI para uma nova importação.';
  if (status === 'modelo_proibido') return 'O modelo configurado para OCR não é permitido. Confira o PDF original e revise a configuração do servidor.';
  if (status === 'indisponivel') return 'Não foi possível acessar o serviço de OCR. Confira a conexão e o PDF original; tente uma nova importação mais tarde.';
  if (status === 'idioma_indisponivel') return 'O idioma necessário para OCR não está disponível neste servidor. Confira o PDF original.';
  if (status === 'falhou') return 'O OCR falhou nesta página. Confira o PDF original e cadastre as questões manualmente, se necessário.';
  if (status === 'limite_excedido') return 'Esta página não foi processada por OCR devido ao limite de processamento. Confira o PDF original.';
  if (page.extraction_method === 'pdf_text') return 'Texto extraído da camada de texto do PDF. Confira a página original.';
  if (page.extraction_method === 'ocr') return 'Texto obtido por OCR. Confira cuidadosamente a página original; o reconhecimento pode conter erros.';
  if (page.extraction_method === 'none') return 'Nenhum texto foi extraído desta página. Confira o PDF original.';
  return 'Origem da extração não registrada. Confira a página original.';
}
function renderImports() {
  const list = $('#import-list'); list.replaceChildren();
  if (!state.documents.length) { list.textContent = 'Nenhum documento importado ainda.'; return; }
  for (const doc of state.documents) {
    const row = element('div', undefined, 'file-row');
    const job = state.jobs.find(item => item.document_id === doc.id);
    const info = element('div'); info.append(element('strong', doc.filename), element('small', `Estado: ${job?.status || doc.status || 'em revisão'}`));
    if (job) info.append(element('small', `IA: ${job.status} · ${job.done}/${job.total} páginas${job.error ? ` · ${job.error}` : ''}`));
    if (job && (job.status === 'falhou' || job.status === 'interrompido' || (job.status === 'parcial' && job.error.includes('Falhas:')))) {
      const retry = element('button', 'Retomar páginas pendentes', 'secondary'); retry.type = 'button';
      retry.addEventListener('click', async () => { retry.disabled = true; try { await api(`/api/documents/${encodeURIComponent(doc.id)}/resume-import`, {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); await refresh(); monitorImport(doc.id); } catch(error) { retry.disabled = false; notice(error.message, true); } });
      info.append(retry);
    }
    if (doc.source_info?.url) { const source = element('a', 'Fonte oficial ↗', 'source-link'); source.href = doc.source_info.url; source.target = '_blank'; source.rel = 'noopener noreferrer'; info.append(source); }
    const pages = Array.isArray(doc.pages) ? doc.pages : [];
    const needsReview = pages.filter(page => ['nao_solicitado', 'configuracao_ausente', 'modelo_proibido', 'sem_texto', 'indisponivel', 'idioma_indisponivel', 'falhou', 'limite_excedido'].includes(page.ocr_status)).length;
    if (needsReview && !job) info.append(element('small', `${needsReview} ${needsReview === 1 ? 'página precisa' : 'páginas precisam'} de atenção na extração.`));
    const button = doc.source_info?.kind === 'gabarito' ? element('a', 'Abrir gabarito', 'secondary') : element('button', 'Revisar', 'secondary');
    if (doc.source_info?.kind === 'gabarito') { button.href = `/api/documents/${encodeURIComponent(doc.id)}/pdf`; button.target = '_blank'; button.rel = 'noopener noreferrer'; const show = element('button', 'Ver versões', 'secondary'); show.type = 'button'; show.addEventListener('click', () => showAnswerKey(doc.id)); info.append(show); }
    else { button.type = 'button'; button.addEventListener('click', () => openReview(doc.id)); }
    row.append(info, button); list.append(row);
  }
}
async function showAnswerKey(id) {
  const target = $('#answer-key-result'); target.replaceChildren(element('p', 'Lendo gabarito…'));
  try {
    const data = await api(`/api/documents/${encodeURIComponent(id)}/answer-keys`);
    const versions = Object.entries(data.versions); target.replaceChildren();
    if (!versions.length) { target.append(element('p', 'Nenhuma versão identificada. Confira o PDF original.', 'field-note')); return; }
    target.append(element('p', 'Versões detectadas; a correspondência com a prova ainda não foi comprovada. Nenhuma resposta foi aplicada.', 'field-note'));
    for (const [name, version] of versions) target.append(element('p', `Versão ${name}: ${Object.keys(version.answers).length} respostas · páginas ${version.pages.join(', ')}${version.conflicts.length ? ` · conflitos: ${version.conflicts.join(', ')}` : ''}`));
  } catch (error) { target.replaceChildren(element('p', error.message, 'error')); }
}
async function loadCatalog() {
  const container = $('#online-catalog'); container.replaceChildren(element('p', 'Carregando catálogo…', 'muted'));
  try {
    const entries = await api('/api/catalog'); container.replaceChildren();
    if (!entries.length) { container.append(element('p', 'Nenhuma prova disponível no catálogo.', 'muted')); return; }
    for (const entry of entries) {
      const card = element('div', undefined, 'file-row'); const description = element('div');
      description.append(element('strong', entry.title), element('p', entry.description, 'muted'));
      const source = element('a', 'Ver concurso na Vunesp ↗', 'source-link'); source.href = entry.contest_url; source.target = '_blank'; source.rel = 'noopener noreferrer'; description.append(source);
      for (const [label, url] of [['Abrir prova oficial ↗', entry.exam_url], ['Abrir gabarito oficial ↗', entry.answer_url]]) { const link = element('a', label, 'source-link'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; description.append(link); }
      const button = element('button', 'Buscar prova e gabarito', 'secondary'); button.type = 'button';
      button.addEventListener('click', async () => {
        button.disabled = true; notice('Buscando documentos na fonte oficial…');
        try { const result = await api('/api/catalog/import', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:entry.id})}); await refresh(); await openReview(result.exam.id); notice(`Documentos recebidos. ${result.warning}`); }
        catch(error) {
          const refused = /403|recusou/i.test(error.message);
          notice(refused ? 'A Vunesp recusou a busca automática. O login pode ser necessário, mas o motivo não foi confirmado. Entre na Vunesp, baixe o PDF e envie-o abaixo.' : `Não foi possível buscar os documentos: ${error.message}`, true);
        } finally { button.disabled = false; }
      });
      card.append(description, button); container.append(card);
    }
  } catch(error) { container.replaceChildren(element('p', `Catálogo indisponível: ${error.message}`, 'error')); }
}
function inputField(labelText, name, required = true, value = '') {
  const wrapper = element('label', labelText); const input = element('input');
  input.name = name; input.type = 'text'; input.required = required; input.value = value;
  wrapper.append(input); return wrapper;
}
async function openReview(id) {
  try {
    notice('');
    const [doc, drafts] = await Promise.all([api(`/api/documents/${encodeURIComponent(id)}`), api(`/api/documents/${encodeURIComponent(id)}/drafts`)]);
    const target = $('#review-content'); target.replaceChildren();
    const card = element('article', undefined, 'card review-card');
    card.append(element('h3', `Revisar: ${doc.filename}`), element('p', 'As questões extraídas são sugestões. Confira o PDF original, inclusive imagens e textos de apoio, antes de publicar.', 'muted'));
    const pages = Array.isArray(doc.pages) ? doc.pages : [];
    const pendingDrafts = drafts.filter(d => d.status === 'em_revisao');
    if (pendingDrafts.length) {
      const checked = pendingDrafts.filter(d => d.batch_review?.status === 'sem_alerta');
      const flagged = pendingDrafts.filter(d => d.batch_review?.status === 'atencao');
      const remaining = pendingDrafts.filter(d => !d.batch_review);
      const batch = element('section', undefined, 'ocr-batch');
      batch.append(element('h3', 'Conferência em lote'), element('p', `${checked.length} sem alerta · ${flagged.length} precisam de atenção · ${remaining.length} ainda não conferidas.`), element('p', 'A conferência visual envia páginas e rascunhos à DeepSeek e pode gerar custos. A IA pode não identificar todos os erros; sem alerta não significa gabarito confirmado. Salve edições antes de começar.', 'muted'));
      const numbers = new Set(drafts.filter(d => /^\d+$/.test(String(d.number))).map(d => Number(d.number)));
      const maxNumber = numbers.size ? Math.max(...numbers) : 0;
      const missing = Array.from({length: Math.min(maxNumber, 200)}, (_, i) => i + 1).filter(n => !numbers.has(n));
      if (missing.length) batch.append(element('p', `Possíveis questões não identificadas: ${missing.join(', ')}. Confira a numeração no PDF.`, 'error'));
      batch.append(element('p', 'A quantidade total de questões não é verificada automaticamente; confira se todas foram identificadas.', 'muted'));
      const progress = element('p', '', 'muted'); progress.setAttribute('role', 'status'); batch.append(progress);
      const run = element('button', 'Conferir páginas pendentes com IA', 'secondary'); run.type = 'button'; run.disabled = !remaining.length;
      run.addEventListener('click', async () => {
        run.disabled = true;
        const pageNumbers = [...new Set(remaining.map(d => d.page))].sort((a,b) => a-b);
        try {
          for (let i=0; i<pageNumbers.length; i++) {
            progress.textContent = `Conferindo página ${pageNumbers[i]} (${i+1} de ${pageNumbers.length})…`;
            await api(`/api/documents/${encodeURIComponent(id)}/batch-review`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({confirm:true,page:pageNumbers[i]})});
          }
          await openReview(id); notice('Conferência concluída. Examine os alertas antes de publicar.');
        } catch(error) { await openReview(id); notice(`Conferência interrompida: ${error.message}. O progresso anterior foi preservado.`, true); }
      });
      const publish = element('button', `Publicar ${checked.length} sem alerta`, 'secondary'); publish.type = 'button'; publish.disabled = !checked.length;
      publish.addEventListener('click', async () => {
        publish.disabled = true;
        try { const result = await api(`/api/documents/${encodeURIComponent(id)}/batch-publish`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true})}); await refresh(); await openReview(id); notice(`${result.published} questões publicadas com conferência automática e sem gabarito.`); }
        catch(error) { notice(error.message, true); publish.disabled = false; }
      });
      batch.append(run, publish);
      if (flagged.length) {
        const summary = element('details'); summary.append(element('summary', `Ver ${flagged.length} questões que precisam de atenção`));
        const list = element('ul'); for (const d of flagged) list.append(element('li', `Questão ${d.number} · página ${d.page}: ${(d.batch_review.reasons || []).join(' ')}`)); summary.append(list); batch.append(summary);
      }
      card.append(batch);
    }
    const pendingOcr = pages.filter(pageNeedsOcr).length;
    if (pendingOcr) {
      const section = element('div', undefined, 'ocr-batch');
      section.append(element('p', `${pendingOcr} ${pendingOcr === 1 ? 'página pendente' : 'páginas pendentes'} de OCR. Ao processar o próximo lote, até 10 imagens de páginas serão enviadas à OpenAI; isso pode gerar custos. Salve eventuais edições antes de continuar.`, 'muted'));
      const button = element('button', 'Processar próximo lote com OCR', 'secondary'); button.type = 'button';
      button.addEventListener('click', async () => {
        button.disabled = true; notice('Processando próximo lote com OCR…');
        try {
          await api(`/api/documents/${encodeURIComponent(id)}/ocr`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({confirm:true})});
          await refresh(); await openReview(id); notice('Lote processado. Confira o estado de cada página.');
        } catch (error) { notice(error.message, true); button.disabled = false; }
      });
      section.append(button); card.append(section);
    }
    const draftLabel = element('label', 'Questão identificada'); const draftSelector = element('select');
    const manual = element('option', 'Nova questão manual'); manual.value = ''; draftSelector.append(manual);
    for (const draft of drafts) {
      const reviewLabel = draft.batch_review?.status === 'sem_alerta' ? 'sem alerta' : draft.batch_review?.status === 'atencao' ? 'atenção' : 'revisar';
      const option = element('option', `Questão ${draft.number} · página ${draft.page} · ${draft.status === 'published' || draft.status === 'publicada' ? 'publicada' : reviewLabel}`);
      option.value = String(draft.id); draftSelector.append(option);
    }
    draftLabel.append(draftSelector); card.append(draftLabel);
    if (!drafts.length) card.append(element('p', 'Nenhuma questão foi identificada automaticamente. Você pode cadastrar uma questão manualmente.', 'muted'));
    const selectorLabel = element('label', 'Página de origem'); const selector = element('select');
    for (const page of pages) { const option = element('option', `Página ${page.page}`); option.value = String(page.page); selector.append(option); }
    selectorLabel.append(selector); card.append(selectorLabel);
    const sourceLink = element('a', 'Abrir página no PDF original ↗', 'source-link'); sourceLink.target = '_blank'; sourceLink.rel = 'noopener noreferrer'; card.append(sourceLink);
    const extracted = element('textarea'); extracted.readOnly = true; extracted.setAttribute('aria-label', 'Texto extraído da página');
    const extractionStatus = element('p', '', 'extraction-status'); extractionStatus.setAttribute('role', 'status');
    const updateText = () => {
      const page = pages.find(p => String(p.page) === selector.value);
      extracted.value = page?.text || 'Nenhum texto extraído nesta página. Confira o PDF original.';
      extractionStatus.textContent = pageExtractionDescription(page);
      extractionStatus.classList.toggle('attention', Boolean(page && ['nao_solicitado', 'configuracao_ausente', 'modelo_proibido', 'sem_texto', 'indisponivel', 'idioma_indisponivel', 'falhou', 'limite_excedido'].includes(page.ocr_status)));
      sourceLink.href = `/api/documents/${encodeURIComponent(id)}/pdf#page=${encodeURIComponent(selector.value)}`;
    };
    selector.addEventListener('change', updateText); updateText(); card.append(extractionStatus, element('p', 'Texto extraído da página', 'muted'), extracted);
    const warnings = element('div', undefined, 'draft-warnings'); card.append(warnings);
    const form = element('form', undefined, 'review-form');
    const row = element('div', undefined, 'row'); row.append(inputField('Número da questão', 'number'), inputField('Matéria', 'subject')); form.append(row);
    const contextLabel = element('label', 'Texto de apoio (opcional)'); const context = element('textarea'); context.name = 'context'; contextLabel.append(context); form.append(contextLabel);
    const contextPageLabel = element('label', 'Página do texto de apoio (opcional)'); const contextPage = element('select'); contextPage.name = 'context_page';
    const noContextPage = element('option', 'Não informada'); noContextPage.value = ''; contextPage.append(noContextPage);
    for (const page of pages) { const option = element('option', `Página ${page.page}`); option.value = String(page.page); contextPage.append(option); }
    contextPageLabel.append(contextPage); form.append(contextPageLabel);
    const contextLink = element('a', 'Abrir página do texto de apoio no PDF ↗', 'source-link'); contextLink.target = '_blank'; contextLink.rel = 'noopener noreferrer'; contextLink.hidden = true; form.append(contextLink);
    const updateContextLink = () => { contextLink.hidden = !contextPage.value; if (contextPage.value) contextLink.href = `/api/documents/${encodeURIComponent(id)}/pdf#page=${encodeURIComponent(contextPage.value)}`; };
    contextPage.addEventListener('change', updateContextLink);
    const promptLabel = element('label', 'Enunciado'); const prompt = element('textarea'); prompt.name = 'prompt'; prompt.required = true; promptLabel.append(prompt); form.append(promptLabel);
    for (let i = 0; i < 5; i++) {
      const label = element('label', `Alternativa ${String.fromCharCode(65 + i)}${i > 1 ? ' (opcional)' : ''}`);
      const input = element('textarea'); input.name = `option${i}`; input.required = i < 2; input.className = 'option-editor'; label.append(input); form.append(label);
    }
    const answerLabel = element('label', 'Gabarito (opcional)'); const answer = element('select'); answer.name = 'answer';
    const unknown = element('option', 'Sem gabarito confirmado'); unknown.value = ''; answer.append(unknown);
    for (let i = 0; i < 5; i++) { const option = element('option', String.fromCharCode(65 + i)); option.value = String(i); answer.append(option); }
    answerLabel.append(answer); form.append(answerLabel, inputField('Origem do gabarito, se informado', 'answer_source', false));
    const confirmation = element('label', undefined, 'confirmation'); const checkbox = element('input'); checkbox.type = 'checkbox'; checkbox.required = true;
    confirmation.append(checkbox, element('span', 'Revisei a questão, as alternativas e a página de origem.')); form.append(confirmation);
    const save = element('button', 'Publicar questão revisada', 'primary'); save.type = 'submit'; form.append(save);
    const selectDraft = () => {
      const draft = drafts.find(d => String(d.id) === draftSelector.value);
      form.reset(); updateContextLink(); warnings.replaceChildren();
      if (!draft) { save.disabled = false; return; }
      selector.value = String(draft.page); updateText();
      form.elements.number.value = draft.number || ''; form.elements.subject.value = draft.subject || ''; form.elements.prompt.value = draft.prompt || ''; form.elements.context.value = draft.context || ''; contextPage.value = draft.context_page ? String(draft.context_page) : ''; updateContextLink();
      (draft.options || []).slice(0, 5).forEach((option, i) => { form.elements[`option${i}`].value = option; });
      const notices = Array.isArray(draft.warnings) ? draft.warnings : [];
      if (notices.length) warnings.append(element('strong', 'Pontos para conferir'), ...notices.map(w => element('p', String(w))));
      if (draft.batch_review) warnings.append(element('p', `Conferência automática: ${draft.batch_review.status === 'sem_alerta' ? 'sem alerta' : (draft.batch_review.reasons || []).join(' ')}`));
      const published = draft.status === 'published' || draft.status === 'publicada';
      if (published) warnings.append(element('p', 'Esta questão já foi publicada.'));
      save.disabled = published;
    };
    draftSelector.addEventListener('change', selectDraft);
    const firstPending = drafts.find(d => d.status !== 'published' && d.status !== 'publicada');
    if (firstPending) { draftSelector.value = String(firstPending.id); selectDraft(); }
    form.addEventListener('submit', async event => {
      event.preventDefault(); const data = new FormData(form);
      const options = Array.from({length: 5}, (_, i) => String(data.get(`option${i}`) || '').trim());
      const selected = data.get('answer') === '' ? null : Number(data.get('answer'));
      if ((selected !== null && !options[selected]) || options.some((v, i) => !v && options.slice(i + 1).some(Boolean))) { notice('Preencha as alternativas em ordem e selecione uma alternativa preenchida.', true); return; }
      if (selected !== null && !String(data.get('answer_source') || '').trim()) { notice('Informe a origem do gabarito ou selecione a opção sem gabarito.', true); return; }
      save.disabled = true;
      try {
        const payload = {document_id: id, page: Number(selector.value), number: String(data.get('number')).trim(), subject: String(data.get('subject')).trim(), prompt: String(data.get('prompt')).trim(), context: String(data.get('context') || '').trim(), context_page: data.get('context_page') ? Number(data.get('context_page')) : null, options: options.filter(Boolean), answer: selected, answer_source: String(data.get('answer_source') || '').trim()};
        const route = draftSelector.value ? `/api/drafts/${encodeURIComponent(draftSelector.value)}/publish` : '/api/questions';
        await api(route, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
        await refresh(); await openReview(id); notice('Questão revisada publicada para estudo.');
      } catch (error) { notice(error.message, true); save.disabled = false; }
    });
    card.append(form); target.append(card); card.scrollIntoView({behavior:'smooth', block:'start'});
  } catch (error) { notice(error.message, true); }
}
function renderQuestion() {
  const content = $('#question-content'); content.replaceChildren();
  const filter = $('#subject-filter');
  const subjects = [...new Set(state.questions.map(q => q.subject).filter(Boolean))].sort((a,b) => a.localeCompare(b, 'pt-BR'));
  filter.replaceChildren(); const all = element('option', 'Todas as matérias'); all.value = ''; filter.append(all);
  for (const subject of subjects) { const option = element('option', subject); option.value = subject; filter.append(option); }
  if (state.subject && !subjects.includes(state.subject)) state.subject = '';
  filter.value = state.subject;
  const questions = state.questions.filter(q => !state.subject || q.subject === state.subject);
  const list = $('#question-list'); list.replaceChildren(); $('#study-count').textContent = `${questions.length} ${questions.length === 1 ? 'questão disponível' : 'questões disponíveis'}`;
  if (!questions.length) { content.append(element('p', 'Nenhuma questão revisada disponível. Importe um PDF e revise uma questão para começar.', 'empty')); return; }
  state.currentQuestion = Math.min(state.currentQuestion, questions.length - 1);
  questions.forEach((item, index) => {
    const button = element('button', `Questão ${item.number} · ${item.subject}`, 'study-item'); button.type = 'button';
    if (index === state.currentQuestion) button.setAttribute('aria-current', 'step');
    button.addEventListener('click', () => { state.currentQuestion = index; renderQuestion(); }); list.append(button);
  });
  const q = questions[state.currentQuestion];
  const wrapper = element('div', undefined, 'question');
  wrapper.append(element('span', `${q.subject || 'Questão'} · ${state.currentQuestion + 1} de ${questions.length}`, 'tag'), element('p', `Questão ${q.number} · documento ${q.document_id} · página ${q.page}`, 'muted'));
  if (q.review_method === 'automatico') wrapper.append(element('p', 'Publicada após conferência automática. A extração pode conter erros.', 'muted'));
  if (q.review_method === 'ia_extracao') wrapper.append(element('p', 'Extraída automaticamente por IA; pode conter erros.', 'muted'));
  const sourceLink = element('a', 'Consultar página da prova original ↗', 'source-link'); sourceLink.href = `/api/documents/${encodeURIComponent(q.document_id)}/pdf#page=${encodeURIComponent(q.page)}`; sourceLink.target = '_blank'; sourceLink.rel = 'noopener noreferrer'; wrapper.append(sourceLink);
  if (q.context_page && q.context_page !== q.page) { const support = element('a', 'Consultar página do texto de apoio ↗', 'source-link'); support.href = `/api/documents/${encodeURIComponent(q.document_id)}/pdf#page=${encodeURIComponent(q.context_page)}`; support.target = '_blank'; support.rel = 'noopener noreferrer'; wrapper.append(support); }
  const visual = q.visual_assets || {};
  for (let i = 0; i < (visual.question || []).length; i++) {
    const image = element('img'); image.src = `/api/questions/${encodeURIComponent(q.id)}/assets/question/${i}.png`; image.alt = `Imagem extraída da questão ${q.number}`; image.loading = 'lazy'; wrapper.append(image);
  }
  if (q.illustration) { const illustration = element('img'); illustration.src = q.illustration.url; illustration.alt = `Ilustração da questão ${q.number}`; illustration.loading = 'lazy'; wrapper.append(illustration); }
  const previewPage = q.page;
  const figure = element('figure', undefined, 'page-preview');
  const img = element('img'); img.src = `/api/questions/${encodeURIComponent(q.id)}/excerpt.png`; img.alt = `Recorte da questão ${q.number} na página ${previewPage} da prova original`; img.loading = 'lazy';
  const expand = element('a', 'Ampliar recorte ↗', 'source-link'); expand.href = img.src; expand.target = '_blank'; expand.rel = 'noopener noreferrer';
  const caption = element('figcaption', `Recorte automático da questão, página ${previewPage}. `); caption.append(expand);
  img.addEventListener('error', () => { figure.hidden = true; });
  figure.append(img, caption); wrapper.append(figure);
  if (q.context) wrapper.append(element('div', q.context, 'question-context'));
  wrapper.append(element('p', q.prompt));
  const form = element('form'); const options = element('div', undefined, 'options');
  (q.options || []).forEach((option, index) => {
    const label = element('label', undefined, 'option'); const radio = element('input'); radio.type = 'radio'; radio.name = 'selected'; radio.value = String(index); radio.required = true;
    label.append(radio, element('span', `${String.fromCharCode(65 + index)}. ${option}`));
    if (visual.options?.[index]) { const image = element('img'); image.src = `/api/questions/${encodeURIComponent(q.id)}/assets/option/${index}.png`; image.alt = `Imagem da alternativa ${String.fromCharCode(65 + index)}`; image.loading = 'lazy'; label.append(image); }
    options.append(label);
  });
  form.append(options); const submit = element('button', 'Responder', 'primary'); submit.type = 'submit'; form.append(submit);
  const result = element('div'); result.setAttribute('role','status');
  form.addEventListener('submit', async event => {
    event.preventDefault(); submit.disabled = true;
    try {
      const attempt = await api('/api/attempts', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question_id:q.id, selected:Number(new FormData(form).get('selected'))})});
      result.className = 'result';
      if (attempt.correct === null || attempt.correct === undefined) result.textContent = 'Resposta registrada. Esta questão ainda não possui gabarito confirmado.';
      else {
        const correctLetter = Number.isInteger(attempt.answer) ? String.fromCharCode(65 + attempt.answer) : null;
        result.textContent = `${attempt.correct ? 'Resposta correta.' : 'Resposta incorreta.'}${correctLetter ? ` Alternativa indicada: ${correctLetter}.` : ''}${attempt.answer_source ? ` Origem informada: ${attempt.answer_source}` : ''}`;
      }
      for (const input of options.querySelectorAll('input')) input.disabled = true;
      await refresh();
    } catch(error) { submit.disabled = false; notice(error.message, true); }
  });
  wrapper.append(form, result);
  const tutor = element('section', undefined, 'tutor-panel');
  tutor.append(element('h3', 'Tutoria com IA'), element('p', 'Ao pedir uma explicação, o enunciado, as alternativas, o texto de apoio e sua pergunta serão enviados à DeepSeek e poderão gerar custos. Confira a resposta e as fontes antes de usá-la.', 'field-note'));
  if (state.settings?.ai_provider !== 'deepseek') {
    tutor.append(element('p', 'Ative a DeepSeek nas configurações para usar a tutoria.', 'muted'));
    const settingsButton = element('button', 'Abrir configurações', 'secondary'); settingsButton.type = 'button'; settingsButton.dataset.go = 'settings'; tutor.append(settingsButton);
  } else {
    const tutorForm = element('form'); const label = element('label', 'Sua pergunta (opcional)'); const question = element('textarea'); question.name = 'question'; question.maxLength = 2000; question.placeholder = 'Por exemplo: explique por que a alternativa está correta.'; label.append(question);
    const ask = element('button', 'Solicitar explicação à DeepSeek', 'secondary'); ask.type = 'submit'; tutorForm.append(label, ask);
    const tutorResult = element('div', undefined, 'tutor-result'); tutorResult.setAttribute('role', 'status');
    tutorForm.addEventListener('submit', async event => {
      event.preventDefault(); ask.disabled = true; tutorResult.replaceChildren(element('p', 'Solicitando explicação…', 'muted'));
      try {
        const reply = await api('/api/tutor', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question_id:q.id, question:question.value.trim()})});
        tutorResult.replaceChildren(element('strong', `Explicação sugerida · ${reply.provider} / ${reply.model}`), element('p', reply.answer), element('p', 'Resposta gerada por IA; verifique as fontes e o gabarito.', 'field-note'));
      } catch (error) { tutorResult.replaceChildren(element('p', error.message, 'error')); } finally { ask.disabled = false; }
    });
    tutor.append(tutorForm, tutorResult);
  }
  wrapper.append(tutor);
  const controls = element('div', undefined, 'study-controls');
  const prev = element('button', '← Anterior', 'secondary'); prev.type = 'button'; prev.disabled = state.currentQuestion === 0;
  prev.addEventListener('click', () => { state.currentQuestion--; renderQuestion(); });
  const next = element('button', 'Próxima →', 'secondary'); next.type = 'button'; next.disabled = state.currentQuestion === questions.length - 1;
  next.addEventListener('click', () => { state.currentQuestion++; renderQuestion(); }); controls.append(prev,next); wrapper.append(controls);
  content.append(wrapper);
}
$('#subject-filter').addEventListener('change', event => { state.subject = event.target.value; state.currentQuestion = 0; renderQuestion(); });
async function refresh() {
  const [documents, questions, attempts, settings, jobs] = await Promise.all([api('/api/documents'), api('/api/questions'), api('/api/attempts'), api('/api/settings'), api('/api/import-jobs')]);
  state.documents = documents; state.questions = questions; state.attempts = attempts; state.settings = settings; state.jobs = jobs; renderDashboard(); renderImports();
}
document.addEventListener('click', event => { const button = event.target.closest('[data-view], [data-go]'); if (button) showView(button.dataset.view || button.dataset.go); });
let activeSimulation = null;
let simulationIndex = 0;
let simulationOffset = 0;
let simulationRefreshing = false;

async function loadSimulations() {
  const items = await api('/api/simulations');
  const list = $('#simulation-list'); list.replaceChildren();
  if (!items.length) list.append(element('p', 'Nenhum simulado criado.', 'muted'));
  for (const item of items) {
    const row = element('div', undefined, 'file-row');
    const info = element('div'); info.append(element('strong', `Simulado ${item.id}`), element('small', `${item.questions.length} questões · ${item.status === 'em_andamento' ? 'Em andamento' : 'Finalizado'}`));
    const open = element('button', item.status === 'em_andamento' ? 'Retomar' : 'Ver resultado', 'secondary'); open.type = 'button'; open.addEventListener('click', () => openSimulation(item.id));
    row.append(info, open); list.append(row);
  }
  const select = $('#simulation-subject'); const previous = select.value; select.replaceChildren();
  const all = element('option', 'Todas as matérias'); all.value = ''; select.append(all);
  for (const subject of [...new Set(state.questions.map(q => q.subject).filter(Boolean))].sort((a,b) => a.localeCompare(b,'pt-BR'))) { const option = element('option', subject); option.value = subject; select.append(option); }
  select.value = previous;
}

async function openSimulation(id, preserveIndex = false) {
  try {
    activeSimulation = await api(`/api/simulations/${encodeURIComponent(id)}`);
    simulationOffset = Date.parse(activeSimulation.server_now) - Date.now();
    if (!preserveIndex) simulationIndex = 0;
    renderSimulation(); await loadSimulations();
  } catch (error) { notice(error.message, true); }
}

function renderSimulation() {
  const target = $('#simulation-content'); target.replaceChildren();
  if (!activeSimulation) return;
  const sim = activeSimulation; const finished = sim.status === 'finalizado';
  const card = element('article', undefined, 'card simulation-card');
  card.append(element('h3', `Simulado ${sim.id}`));
  const timer = element('p', '', 'muted'); timer.id = 'simulation-timer'; card.append(timer);
  if (finished) {
    const r = sim.result;
    card.append(element('p', `Resultado: ${r.acertos} ${r.acertos === 1 ? 'acerto' : 'acertos'} · ${r.erros} ${r.erros === 1 ? 'erro' : 'erros'} · ${r.sem_gabarito} sem gabarito · ${r.nao_respondidas} não respondidas.`));
  }
  simulationIndex = Math.max(0, Math.min(simulationIndex, sim.questions.length - 1));
  const q = sim.questions[simulationIndex];
  if (!q) { target.append(card); return; }
  const answered = sim.questions.filter(item => item.selected !== null && item.selected !== undefined).length;
  card.append(element('p', `Questão ${simulationIndex + 1} de ${sim.questions.length} · ${answered} ${answered === 1 ? 'respondida' : 'respondidas'} · ${q.subject}`, 'muted'));
  if (q.context) card.append(element('div', q.context, 'question-context'));
  card.append(element('p', q.prompt));
  const visual = q.visual_assets || {};
  const original = state.questions.find(item => item.id === q.id);
  if (original?.illustration) { const image = element('img', undefined, 'simulation-image'); image.src = original.illustration.url; image.alt = `Ilustração da questão ${q.number}`; card.append(image); }
  for (let i=0; i<(visual.question || []).length; i++) { const image = element('img', undefined, 'simulation-image'); image.src = `/api/questions/${encodeURIComponent(q.id)}/assets/question/${i}.png`; image.alt = `Imagem da questão ${q.number}`; card.append(image); }
  const options = element('div', undefined, 'options');
  (q.options || []).forEach((option,index) => {
    const label = element('label', undefined, 'option'); const radio = element('input'); radio.type = 'radio'; radio.name = 'simulation-answer'; radio.value = String(index); radio.checked = q.selected === index; radio.disabled = finished;
    label.append(radio, element('span', `${String.fromCharCode(65+index)}. ${option}`));
    if (visual.options?.[index]) { const image = element('img'); image.src = `/api/questions/${encodeURIComponent(q.id)}/assets/option/${index}.png`; image.alt = `Imagem da alternativa ${String.fromCharCode(65+index)}`; label.append(image); }
    radio.addEventListener('change', async () => {
      for (const input of options.querySelectorAll('input')) input.disabled = true;
      try { activeSimulation = await api(`/api/simulations/${encodeURIComponent(sim.id)}/answer`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_id:q.id,selected:index})}); simulationOffset = Date.parse(activeSimulation.server_now)-Date.now(); renderSimulation(); }
      catch (error) { notice(error.message, true); await openSimulation(sim.id, true); }
    });
    options.append(label);
  });
  card.append(options);
  if (!finished && q.selected !== null && q.selected !== undefined) {
    const clear = element('button','Limpar resposta','secondary'); clear.type='button';
    clear.addEventListener('click',async()=>{clear.disabled=true;try {activeSimulation=await api(`/api/simulations/${encodeURIComponent(sim.id)}/answer`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question_id:q.id,selected:null})}); simulationOffset=Date.parse(activeSimulation.server_now)-Date.now();renderSimulation();} catch(error){notice(error.message,true);await openSimulation(sim.id,true);} }); card.append(clear);
  }
  if (finished) {
    let message = q.selected === null || q.selected === undefined ? 'Não respondida.' : q.answer === null ? 'Resposta registrada; questão sem gabarito confirmado.' : q.correct ? 'Resposta correta.' : 'Resposta incorreta.';
    if (q.answer !== null && q.answer !== undefined) message += ` Gabarito: ${String.fromCharCode(65+q.answer)}.${q.answer_source ? ` Fonte: ${q.answer_source}` : ''}`;
    card.append(element('p', message, 'result'));
  }
  const controls = element('div', undefined, 'study-controls');
  const prev = element('button', '← Anterior', 'secondary'); prev.type='button'; prev.disabled=simulationIndex===0; prev.addEventListener('click',()=>{simulationIndex--;renderSimulation();});
  const next = element('button', 'Próxima →', 'secondary'); next.type='button'; next.disabled=simulationIndex===sim.questions.length-1; next.addEventListener('click',()=>{simulationIndex++;renderSimulation();});
  controls.append(prev,next);
  if (!finished) {
    const finish = element('button', 'Finalizar simulado', 'primary'); finish.type='button';
    finish.addEventListener('click',async()=>{finish.disabled=true;try { activeSimulation=await api(`/api/simulations/${encodeURIComponent(sim.id)}/finish`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});renderSimulation();await loadSimulations(); } catch(error){notice(error.message,true);finish.disabled=false;} }); controls.append(finish);
  }
  card.append(controls); target.append(card); updateSimulationTimer();
}

function updateSimulationTimer() {
  const timer = $('#simulation-timer'); if (!timer || !activeSimulation) return;
  if (activeSimulation.status === 'finalizado') { timer.textContent = 'Simulado finalizado.'; return; }
  const seconds = Math.max(0, Math.ceil((Date.parse(activeSimulation.deadline) - (Date.now()+simulationOffset))/1000));
  timer.textContent = `Tempo restante: ${String(Math.floor(seconds/3600)).padStart(2,'0')}:${String(Math.floor(seconds%3600/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
  if (!seconds && !simulationRefreshing) { simulationRefreshing=true; openSimulation(activeSimulation.id,true).finally(()=>{simulationRefreshing=false;}); }
}
setInterval(updateSimulationTimer, 1000);

$('#simulation-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.currentTarget.querySelector('button'); button.disabled=true;
  try { const sim = await api('/api/simulations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quantidade:Number($('#simulation-count').value),duracao_minutos:Number($('#simulation-duration').value),materia:$('#simulation-subject').value})}); activeSimulation=sim; simulationOffset=Date.parse(sim.server_now)-Date.now();simulationIndex=0;renderSimulation();await loadSimulations();notice('Simulado iniciado.'); }
  catch(error){notice(error.message,true);} finally {button.disabled=false;}
});

$('#upload-form').addEventListener('submit', async event => {
  event.preventDefault(); const file = $('#pdf').files[0]; if (!file) return;
  if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') { notice('Selecione um arquivo PDF.', true); return; }
  const form = event.currentTarget; const submit = form.querySelector('button'); submit.disabled = true; notice('Enviando e preparando documento. Páginas digitalizadas podem levar mais tempo…');
  try { const doc = await api('/api/documents', {method:'POST',headers:{'Content-Type':'application/pdf','X-Filename':encodeURIComponent(file.name),'X-Auto-Extract':'true'},body:file}); form.reset(); await refresh(); notice('Documento recebido. A extração com IA começou.'); monitorImport(doc.id); }
  catch(error) { notice(error.message, true); } finally { submit.disabled = false; }
});
async function monitorImport(id) {
  const progress = $('#import-progress');
  try {
    const job = await api(`/api/documents/${encodeURIComponent(id)}/import-job`);
    progress.textContent = `Extração: ${job.done} de ${job.total} páginas. ${job.error || ''}`;
    if (job.status === 'processando') { setTimeout(() => monitorImport(id), 3000); return; }
    await refresh();
    notice(job.status === 'concluido' ? 'Extração concluída. As questões estão disponíveis para estudo.' : `Extração ${job.status}. ${job.error || ''}`, job.status !== 'concluido');
  } catch (error) { progress.textContent = `Não foi possível acompanhar a importação: ${error.message}`; }
}
$('#answer-key-form').addEventListener('submit', async event => {
  event.preventDefault(); const file = $('#answer-key-pdf').files[0]; if (!file) return;
  const button = event.currentTarget.querySelector('button'); button.disabled = true;
  try { const doc = await api('/api/documents', {method:'POST', headers:{'Content-Type':'application/pdf','X-Filename':encodeURIComponent(file.name),'X-Document-Kind':'gabarito'}, body:file}); event.currentTarget.reset(); await refresh(); await showAnswerKey(doc.id); notice('Gabarito recebido para análise.'); }
  catch (error) { notice(error.message, true); } finally { button.disabled = false; }
});
refresh().catch(error => notice(`Não foi possível carregar os dados: ${error.message}`, true));
setInterval(() => { if (state.jobs.some(job => job.status === 'processando')) refresh().catch(() => {}); }, 5000);
