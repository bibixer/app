// 1. Data and Initialization

function fillJobInfo() {
  document.getElementById("jobName").innerText = JOB_CARD.name;
  document.getElementById("jobDate").innerText = JOB_CARD.date;
}

// 2. Render Table with correct classes for JS targeting
function renderTable(items) {
  const tbody = document.querySelector("#returnTable tbody");
  tbody.innerHTML = items
    .map((item, index) => {
      const remaining = item.issued;
      const historyHtml =
        item.history
          .map(
            (h) =>
              `<div class="history-item">📅 ${h.date} — Returned <b>${h.returned}</b> pcs</div>`,
          )
          .join("") || '<div class="history-item">No previous returns</div>';

      return `
                   <tr>
                     <td><span class="id-badge">#${item.item_id}</span></td>
                     <td class="name-badge">
                       <div style="font-weight:600">${item.name}</div>
                       <div class="history-toggle" onclick="toggleHistory(${index})">
             <!--            <span class="chevron" id="chevron-${index}">▶</span> View History-->
                       </div>
                       <div class="history-content" id="history-${index}">${historyHtml}</div>
                     </td>
                     <td class="item-colour">${item.colour}</td>
                     <td><span class="remaining-badge ${
                       remaining < 10 ? "low" : ""
                     }">${remaining} pcs</span></td>
                     <td>
                       <input type="number" class="return-input"
                              min="0" max="${remaining}"
                              placeholder="0"
                              data-remaining="${remaining}">
                     </td>
                   </tr>
                 `;
    })
    .join("");
}

// 3. Helper for smooth keyboard navigation
function focusAtEnd(input) {
  if (!input) return;
  input.focus();
  // For number inputs, setSelectionRange isn't supported,
  // but focusing is usually enough.
}

// 4. Main Event Listener
document.addEventListener("DOMContentLoaded", () => {
  fillJobInfo();
  renderTable(JOB_CARD.items);

  const getInputs = () =>
    Array.from(document.querySelectorAll(".return-input"));

  // Auto-focus first input
  const first = getInputs()[0];
  if (first) focusAtEnd(first);

  // Keyboard Navigation Logic
  document.addEventListener("keydown", (e) => {
    const el = document.activeElement;
    if (!el || !el.classList.contains("return-input")) return;

    const inputs = getInputs();
    const index = inputs.indexOf(el);

    // ENTER: Move to next row
    if (e.key === "Enter") {
      e.preventDefault();
      if (index < inputs.length - 1) {
        focusAtEnd(inputs[index + 1]);
      } else {
        document.querySelector(".btn-submit")?.focus();
      }
    }

    // BACKSPACE: Move to previous row if current is empty
    if (e.key === "Backspace" && el.value === "") {
      if (index > 0) {
        e.preventDefault();
        focusAtEnd(inputs[index - 1]);
      }
    }
  });
});

// Toggle History Function
function toggleHistory(index) {
  const content = document.getElementById(`history-${index}`);
  const chevron = document.getElementById(`chevron-${index}`);
  const isVisible = content.style.display === "block";
  content.style.display = isVisible ? "none" : "block";
  chevron.classList.toggle("open", !isVisible);
}
async function submitReturn() {
  // 1️⃣ Target all rows in the table body
  const rows = document.querySelectorAll("#returnTable tbody tr");
  const items = [];

  // 2️⃣ Collect data from rows
  rows.forEach((row) => {
    const input = row.querySelector(".return-input");
    if (!input) return;

    const itemId = row.querySelector(".id-badge").innerText.replace("#", "");
    const itemtype = row
      .querySelector(".item-colour")
      .innerText.replace("#", "");
    const remaining = Number(input.dataset.remaining);
    const returnedValue = Number(input.value) || 0;

    const name = row.querySelector(".name-badge").innerText;

    items.push({
      item_id: itemId,
      returned: returnedValue,
      type_R: itemtype,
      remaining,
      name,
    });
  });

  // 3️⃣ Validation
  for (const item of items) {
    if (item.returned < 0) {
      alert(`Item #${item.item_id}: Returned amount cannot be negative.`);
      return;
    }

    if (item.returned > item.remaining) {
      alert(
        `Item #${item.item_id}: Returned pieces (${item.returned}) cannot exceed remaining pieces (${item.remaining}).`,
      );
      return;
    }
  }

  // 4️⃣ Construct payload
  const payload = {
    //  job_card_id: JOB_CARD.id,
    name: JOB_CARD.name,
    items: items
      .filter((item) => item.returned > 0)
      .map((item) => ({
        item_id: item.item_id,
        returned: item.returned,
        name_of_product: item.name,
        type: item.type_R,
      })),
  };

  // 5️⃣ Final check
  if (payload.items.length === 0) {
    alert("Please enter at least one return quantity.");
    return;
  }

  // 6️⃣ Example async call (optional)
  //  <!--  console.log("FINAL PAYLOAD:", payload);-->

  // Uncomment when API is ready

  const response = await fetch("/summit-retune", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data_R = await response.json();
  if (data_R.success) {
    window.location.replace("/retune_product?ok=101");
  }
  if (!data_R.success) {
    window.location.replace("/retune_product?ok=401");
  }
}

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
    e.preventDefault(); // optional but recommended
    submitReturn();
  }
});
