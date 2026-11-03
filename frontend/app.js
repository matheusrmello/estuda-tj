'use strict';

const $ = (selector, root = document) => root.querySelector(selector);
const state = { questions: [], attempts: [], documents: [], settings: null, currentQuestion: 0, subject: '' };

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
  if (name === 'imports') renderImports();
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
    const info = element('div'); info.append(element('strong', doc.filename), element('small', `Estado: ${doc.status || 'em revisão'}`));
    const pages = Array.isArray(doc.pages) ? doc.pages : [];
    const needsReview = pages.filter(page => ['nao_solicitado', 'configuracao_ausente', 'modelo_proibido', 'sem_texto', 'indisponivel', 'idioma_indisponivel', 'falhou', 'limite_excedido'].includes(page.ocr_status)).length;
    if (needsReview) info.append(element('small', `${needsReview} ${needsReview === 1 ? 'página precisa' : 'páginas precisam'} de atenção na extração.`));
    const button = element('button', 'Revisar', 'secondary'); button.type = 'button';
    button.addEventListener('click', () => openReview(doc.id));
    row.append(info, button); list.append(row);
  }
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
      const option = element('option', `Questão ${draft.number} · página ${draft.page} · ${draft.status === 'published' || draft.status === 'publicada' ? 'publicada' : 'revisar'}`);
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
  const sourceLink = element('a', 'Consultar página da prova original ↗', 'source-link'); sourceLink.href = `/api/documents/${encodeURIComponent(q.document_id)}/pdf#page=${encodeURIComponent(q.page)}`; sourceLink.target = '_blank'; sourceLink.rel = 'noopener noreferrer'; wrapper.append(sourceLink);
  if (q.context_page && q.context_page !== q.page) { const support = element('a', 'Consultar página do texto de apoio ↗', 'source-link'); support.href = `/api/documents/${encodeURIComponent(q.document_id)}/pdf#page=${encodeURIComponent(q.context_page)}`; support.target = '_blank'; support.rel = 'noopener noreferrer'; wrapper.append(support); }
  const previewPage = q.illustration?.page || q.context_page || q.page;
  const figure = element('figure', undefined, 'page-preview');
  const img = element('img'); img.src = q.illustration ? q.illustration.url : `/api/documents/${encodeURIComponent(q.document_id)}/pages/${encodeURIComponent(previewPage)}.png`; img.alt = q.illustration ? `Charge da questão ${q.number}, recortada da página ${previewPage} da prova original` : `Página ${previewPage} da prova original, incluindo imagens e texto de apoio`; img.loading = 'lazy';
  const expand = element('a', q.illustration ? 'Ampliar charge ↗' : 'Ampliar página ↗', 'source-link'); expand.href = img.src; expand.target = '_blank'; expand.rel = 'noopener noreferrer';
  const caption = element('figcaption', q.illustration ? `Charge da página ${previewPage} da prova original. ` : `Página ${previewPage} da prova original. Para imagens e charges, consulte a página completa. `); caption.append(expand);
  img.addEventListener('error', () => { img.hidden = true; caption.textContent = 'Não foi possível mostrar a página. Use o link para consultar o PDF original.'; });
  figure.append(img, caption); wrapper.append(figure);
  if (q.context) wrapper.append(element('div', q.context, 'question-context'));
  wrapper.append(element('p', q.prompt));
  const form = element('form'); const options = element('div', undefined, 'options');
  (q.options || []).forEach((option, index) => {
    const label = element('label', undefined, 'option'); const radio = element('input'); radio.type = 'radio'; radio.name = 'selected'; radio.value = String(index); radio.required = true;
    label.append(radio, element('span', `${String.fromCharCode(65 + index)}. ${option}`)); options.append(label);
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
  const [documents, questions, attempts, settings] = await Promise.all([api('/api/documents'), api('/api/questions'), api('/api/attempts'), api('/api/settings')]);
  state.documents = documents; state.questions = questions; state.attempts = attempts; state.settings = settings; renderDashboard(); renderImports();
}
document.addEventListener('click', event => { const button = event.target.closest('[data-view], [data-go]'); if (button) showView(button.dataset.view || button.dataset.go); });
$('#upload-form').addEventListener('submit', async event => {
  event.preventDefault(); const file = $('#pdf').files[0]; if (!file) return;
  if (!file.name.toLowerCase().endsWith('.pdf') && file.type !== 'application/pdf') { notice('Selecione um arquivo PDF.', true); return; }
  const form = event.currentTarget; const submit = form.querySelector('button'); submit.disabled = true; notice('Enviando e preparando documento. Páginas digitalizadas podem levar mais tempo…');
  try { const doc = await api('/api/documents', {method:'POST',headers:{'Content-Type':'application/pdf','X-Filename':encodeURIComponent(file.name),'X-Enable-OCR': $('#enable-ocr').checked ? 'true' : 'false'},body:file}); form.reset(); await refresh(); notice('Documento recebido. Revise o conteúdo antes de estudar.'); await openReview(doc.id); }
  catch(error) { notice(error.message, true); } finally { submit.disabled = false; }
});
refresh().catch(error => notice(`Não foi possível carregar os dados: ${error.message}`, true));
