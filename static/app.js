"use strict";
document.querySelectorAll("form[data-confirm]").forEach(form => form.addEventListener("submit", event => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); }));
const notes = document.querySelector("#notes-form");
let dirty = false;
const savedForm = document.querySelector("#feedback-form");
if (savedForm) {
  savedForm.addEventListener("input", () => { dirty = true; });
  savedForm.addEventListener("submit", () => { dirty = false; });
  window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
}
async function generate(form, button, status) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "正在整理反馈…";
  status.textContent = "通常需要几秒，请稍候。";
  try {
    const response = await fetch(form.dataset.endpoint, { method: "POST", body: new FormData(form), credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } });
    if (response.redirected) throw new Error("登录已过期，请复制当前笔记后重新登录。");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "生成失败，请稍后重试。");
    status.textContent = "已生成，请检查事实后采用。";
    return data.text;
  } catch (error) {
    status.textContent = error.message || "连接失败，课堂输入仍保留，请重试。";
    return null;
  } finally { button.disabled = false; button.textContent = original; }
}
if (notes) {
  notes.addEventListener("input", () => { dirty = true; });
  notes.addEventListener("submit", async event => {
    event.preventDefault();
    const text = await generate(notes, document.querySelector("#generate-button"), document.querySelector("#generation-status"));
    if (text !== null) {
      document.querySelector("#candidate-text").textContent = text;
      document.querySelector("#candidate-box").hidden = false;
      dirty = true;
      document.querySelector("#candidate-box").scrollIntoView({ block: "nearest", behavior: "auto" });
    }
  });
  document.querySelector("#adopt-candidate").addEventListener("click", () => {
    const target = document.querySelector("#id_text");
    if (target.value.trim() && !window.confirm("将编辑区替换为新候选？已保存的反馈会在你点击保存后才更新。")) return;
    target.value = document.querySelector("#candidate-text").textContent;
    document.querySelector("#candidate-box").hidden = true;
    dirty = true; target.focus();
  });
  document.querySelector("#discard-candidate").addEventListener("click", () => { document.querySelector("#candidate-box").hidden = true; });
  document.querySelector("#copy-feedback").addEventListener("click", async () => {
    const text = document.querySelector("#id_text");
    const status = document.querySelector("#copy-status");
    if (!text.value.trim()) { status.textContent = "请先填写或生成反馈。"; return; }
    try { await navigator.clipboard.writeText(text.value); status.textContent = "已复制，可以粘贴给家长。"; }
    catch { text.focus(); text.select(); status.textContent = "已选中文本，请长按或使用快捷键复制。"; }
  });
}
const test = document.querySelector("#test-model");
if (test) test.addEventListener("submit", async event => {
  event.preventDefault();
  const text = await generate(test, test.querySelector("button"), document.querySelector("#test-status"));
  if (text !== null) document.querySelector("#test-output").textContent = text;
});
