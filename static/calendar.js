"use strict";
(() => {
  const calendar = document.querySelector(".interactive-calendar");
  if (!calendar) return;
  const dialog = document.querySelector("#slot-dialog");
  const start = document.querySelector("#slot-start");
  const end = document.querySelector("#slot-end");
  const day = document.querySelector("#slot-date");
  const student = document.querySelector("#slot-student");
  const fullForm = document.querySelector("#slot-full-form");
  function updateRange() {
    end.setCustomValidity(end.value && start.value && end.value <= start.value ? "结束时间必须晚于开始时间。" : "");
    if (fullForm) {
      const query = new URLSearchParams({ date: day.value, start: start.value, end: end.value, student: student.value });
      fullForm.href = "/lessons/new/?" + query.toString();
    }
  }
  calendar.querySelectorAll(".time-slot").forEach(slot => slot.addEventListener("click", event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || typeof dialog.showModal !== "function") return;
    event.preventDefault();
    day.value = slot.dataset.date; start.value = slot.dataset.start; end.value = slot.dataset.end;
    updateRange(); dialog.showModal();
  }));
  [start, end, day, student].forEach(field => field.addEventListener("input", updateRange));
  document.querySelector("#close-slot-dialog").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", event => {
    const box = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom)) dialog.close();
  });
  document.querySelectorAll(".day-tab").forEach(tab => tab.addEventListener("click", event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    const selected = tab.dataset.day;
    document.querySelectorAll(".day-tab, .day-head, .day-column").forEach(item => {
      const active = item.dataset.day === selected;
      item.classList.toggle("is-active", active);
      if (item.classList.contains("day-tab")) {
        if (active) item.setAttribute("aria-current", "date"); else item.removeAttribute("aria-current");
      }
    });
    history.replaceState(null, "", tab.href);
  }));
})();
