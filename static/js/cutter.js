(function () {
        // ------------------------------------------------------------------
        // BACKEND DATA - keeping original structure
        // ------------------------------------------------------------------
        const backendResponse =  data_F
        backendResponse.date_from = new Date(backendResponse.date_from);
        backendResponse.date_to = new Date(backendResponse.date_to);
        backendResponse.tres.forEach((entry) => {
          entry.entry_datetime = new Date(entry.entry_datetime);
        });

        const { name, date_from, date_to, tres } = backendResponse;


// ------------------------------------------------------------------
        // PRODUCTION VIEW CODE (unchanged)
        // ------------------------------------------------------------------
        const diffTime = Math.abs(date_to - date_from);
        const CALENDAR_DAYS = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
        const uniqueWorkingDates = new Set(
          tres.map((e) => e.entry_datetime.toDateString()),
        );
        const ACTUAL_WORKING_DAYS = uniqueWorkingDates.size;
        let WORKING_DAYS = ACTUAL_WORKING_DAYS;
        let isManualOverride = false;

        const startStr = date_from.toLocaleDateString("en-IN", {
          day: "numeric",
          month: "short",
          year: "numeric",
        });
        const endStr = date_to.toLocaleDateString("en-IN", {
          day: "numeric",
          month: "short",
          year: "numeric",
        });

        document.getElementById("dateRangeBadge").innerHTML = `
            <span class="badge-item"><i class="fas fa-user"></i> ${name}</span>
            <span class="badge-item"><i class="fas fa-calendar-alt"></i> ${startStr} – ${endStr}</span>
            <span class="badge-item" style="background: #f0f7ff; padding: 0.3rem 1.2rem; border-radius: 40px;">
                <i class="fas fa-calendar-check"></i>
                <span style="display: flex; align-items: center; gap: 8px;">
                    <span>Working days:</span>
                    <input type="number" id="workingDaysInput" value="${WORKING_DAYS}" min="1" max="${CALENDAR_DAYS}"
                           style="width: 60px; padding: 0.2rem 0.5rem; border: 2px solid #3b82f6; border-radius: 30px;
                                  font-weight: 600; text-align: center; background: white;"
                           onchange="handleWorkingDaysChange(this.value)">
                    <span class="days-chip" style="background: #e4edfb; padding: 0.2rem 1rem;"><i class="far fa-clock"></i> ${CALENDAR_DAYS} total</span>
                    <span id="workingDaysStatus" style="font-size: 0.8rem; color: #2563eb; font-weight: 500;">(from data)</span>
                </span>
            </span>
        `;

        window.handleWorkingDaysChange = function (value) {
          const newValue = parseInt(value);
          if (newValue >= 1 && newValue <= CALENDAR_DAYS) {
            WORKING_DAYS = newValue;
            isManualOverride = newValue !== ACTUAL_WORKING_DAYS;
            const statusSpan = document.getElementById("workingDaysStatus");
            if (isManualOverride) {
              statusSpan.innerHTML = "(manual override)";
              statusSpan.style.color = "#dc2626";
            } else {
              statusSpan.innerHTML = "(from data)";
              statusSpan.style.color = "#2563eb";
            }
            updateWageAndProductivity();
            document
              .querySelector(".wage-card")
              .classList.add("highlight-update");
            setTimeout(
              () =>
                document
                  .querySelector(".wage-card")
                  .classList.remove("highlight-update"),
              500,
            );
          }
        };

        const resetButton = document.createElement("button");
        resetButton.innerHTML = '<i class="fas fa-undo"></i>';
        resetButton.style =
          "background: none; border: none; color: #2563eb; cursor: pointer; font-size: 1rem; margin-left: 5px;";
        resetButton.title = "Reset to actual working days";
        resetButton.onclick = function () {
          document.getElementById("workingDaysInput").value =
            ACTUAL_WORKING_DAYS;
          WORKING_DAYS = ACTUAL_WORKING_DAYS;
          isManualOverride = false;
          document.getElementById("workingDaysStatus").innerHTML =
            "(from data)";
          document.getElementById("workingDaysStatus").style.color = "#2563eb";
          updateWageAndProductivity();
        };
        setTimeout(() => {
          const statusSpan = document.getElementById("workingDaysStatus");
          if (statusSpan) statusSpan.parentNode.appendChild(resetButton);
        }, 100);

        document.getElementById("workDaysDisplay").innerText = WORKING_DAYS;

        // Group production data
        // Group production data
const groups = {};
tres.forEach((entry) => {
  // FIX: Check for entries WITHOUT lump_id OR with type_B containing 'goodCUT'
  // Production entries are those with type_B 'goodCUT 20 picset' and no given_to
  if (!entry.lump_id || entry.type_B !== '') {
    const product = entry.product.trim();
    const type = entry.type_B || "unknown";
    const pieces = entry.pieces;
    if (!groups[product]) groups[product] = {};
    if (!groups[product][type]) groups[product][type] = {};
    if (!groups[product][type][pieces]) {
      groups[product][type][pieces] = {
        count: 0,
        total: 0,
        entries: [],
      };
    }

    groups[product][type][pieces].count += 1;
    groups[product][type][pieces].entries.push({
  id: entry.id,
  entry_datetime: entry.entry_datetime,
  pieces: entry.pieces,
  kg: entry.kg,
  status: entry.status,
  given_to: entry.given_to,
  cutter: entry.cutter,  // This line is crucial
});
  }
});

        Object.keys(groups).forEach((product) => {
          Object.keys(groups[product]).forEach((type) => {
            Object.keys(groups[product][type]).forEach((pieces) => {
              groups[product][type][pieces].total =
                groups[product][type][pieces].count * parseInt(pieces);
            });
          });
        });

        const productTotals = {};
        const productCutDetails = {};
        Object.entries(groups).forEach(([product, typeGroups]) => {
          productTotals[product] = 0;
          productCutDetails[product] = {};
          Object.entries(typeGroups).forEach(([type, piecesGroups]) => {
            let typeTotal = 0;
            Object.values(piecesGroups).forEach(
              (group) => (typeTotal += group.total),
            );
            productTotals[product] += typeTotal;
            productCutDetails[product][type] = typeTotal;
          });
        });

        const sortedProducts = Object.entries(productTotals)
          .sort((a, b) => b[1] - a[1])
          .map((entry) => entry[0]);
        const GRAND_TOTAL = Object.values(productTotals).reduce(
          (sum, val) => sum + val,
          0,
        );

        // Render production table
        const tbody = document.getElementById("tableBody");
        const rowState = {};
        sortedProducts.forEach((product) => {
          const typeGroups = groups[product];
          let firstRow = true;
          Object.entries(typeGroups).forEach(([type, piecesGroups]) => {
            Object.entries(piecesGroups).forEach(([pieces, group]) => {
              const { count, total, entries } = group;
              const groupKey = `${product}|${type}|${pieces}`;
              const isExpanded = rowState[groupKey] || false;

              const mainRow = document.createElement("tr");
              mainRow.setAttribute("data-group", groupKey);
              mainRow.innerHTML = `
                        <td><span class="expand-icon" onclick="toggleDetails('${groupKey}')"><i class="fas ${isExpanded ? "fa-chevron-down" : "fa-chevron-right"}"></i></span></td>
                        <td style="font-weight: ${firstRow ? "600" : "400"};">${firstRow ? product : ""}</td>
                        <td><span class="cut-badge">${type}</span></td>
                        <td>${pieces}</td>
                        <td>${count}</td>
                        <td><strong>${total}</strong></td>
                    `;
              tbody.appendChild(mainRow);

              const totalPieces = entries.reduce((sum, e) => sum + e.pieces, 0);
              const totalKg = entries.reduce((sum, e) => sum + e.kg, 0);
              const avgKgPerPiece =
                totalPieces > 0 ? (totalKg / totalPieces).toFixed(2) : 0;

              const detailRow = document.createElement("tr");
              detailRow.classList.add("details-row");
              detailRow.setAttribute("data-details", groupKey);
              detailRow.style.display = isExpanded ? "table-row" : "none";

              const entryList = entries
  .map((e) => {
    const dateStr = e.entry_datetime.toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
    });
    const kgPerPiece = e.pieces > 0 ? (e.kg / e.pieces).toFixed(2) : 0;

    // Get cutter name (handle both string and object cases)
    const cutterName = e.cutter ?
      (typeof e.cutter === 'object' ? e.cutter.name || JSON.stringify(e.cutter) : e.cutter)
      : "—";

    // Truncate long cutter names
    const displayCutter = cutterName.length > 15 ? cutterName.substring(0, 12) + "…" : cutterName;

    return `<div class="entry-item">
      <div class="entry-row">
        <span class="entry-id">#${e.id}</span>
        <span class="entry-date">${dateStr}</span>
        <span class="entry-pieces">📦 ${e.pieces} pcs</span>
        <span class="entry-kg">⚖️ ${e.kg} kg</span>
        <span class="entry-kg-per-pc">📊 ${kgPerPiece} kg/pc</span>
        <span class="entry-given">👤 ${e.given_to ? e.given_to.substring(0, 15) + "…" : "—"}</span>
        <span class="cutby" style="background:#e2edfe; padding:3px 12px; border-radius:20px;">
          ✂️ ${displayCutter}
        </span>
        <span class="entry-status ${e.status?.toLowerCase() === 'ready' ? 'completed' : e.status?.toLowerCase() || ''}">
          ${e.status || "—"}
        </span>
      </div>
    </div>`;
  })
  .join("");

              detailRow.innerHTML = `<td colspan="8" style="padding: 16px; background: #f8fafc;"><div class="details-vertical-container">
                        <div class="group-summary-vertical">
                            <span class="summary-total">📋 Total: ${count} entries</span>
                            <span class="summary-pieces">📦 Pieces: ${totalPieces}</span>
                            <span class="summary-kg">⚖️ KG: ${totalKg.toFixed(2)}</span>
                            <span class="summary-avg">📊 Avg: ${avgKgPerPiece} kg/pc</span>
                        </div>
                        <div class="entries-vertical-list">${entryList}</div>
                    </div></td>`;
              tbody.appendChild(detailRow);
              firstRow = false;
            });
          });

          const subRow = document.createElement("tr");
          subRow.classList.add("subtotal-row");
          subRow.innerHTML = `<td></td><td colspan="4" style="text-align: right; font-weight: 600;">${product} subtotal →</td><td style="font-weight: 700; background: #e5efff;">${productTotals[product]}</td>`;
          tbody.appendChild(subRow);
          tbody.appendChild(document.createElement("tr")).innerHTML =
            `<td colspan="6" style="border-bottom: 2px dashed #c6daf5;"></td>`;
        });

        document.getElementById("grandTotalValue").innerText = GRAND_TOTAL;

        window.toggleDetails = function (groupKey) {
          const mainRow = document.querySelector(
            `tr[data-group="${groupKey}"]`,
          );
          const detailRow = document.querySelector(
            `tr[data-details="${groupKey}"]`,
          );
          const icon = mainRow.querySelector(".expand-icon i");
          if (detailRow.style.display === "none") {
            detailRow.style.display = "table-row";
            icon.classList.remove("fa-chevron-right");
            icon.classList.add("fa-chevron-down");
            rowState[groupKey] = true;
          } else {
            detailRow.style.display = "none";
            icon.classList.remove("fa-chevron-down");
            icon.classList.add("fa-chevron-right");
            rowState[groupKey] = false;
          }
        };

        // Wage & productivity
        const dailyWageInput = document.getElementById("dailyWageInput");
        const perDayCostSpan = document.getElementById("perDayCost");
        const totalWageCostSpan = document.getElementById("totalWageCost");
        const piecesPerDaySpan = document.getElementById("piecesPerDay");
        const costPerPieceSpan = document.getElementById("costPerPiece");
        const costBox = document.getElementById("costPerPieceBox");
        let lastCostPerPiece = null;

        function formatIndianRupee(value, decimals = 0) {
          return value.toLocaleString("en-IN", {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
          });
        }

        function updateWageAndProductivity() {
          let dailyWage = parseFloat(dailyWageInput.value) || 0;
          if (dailyWage < 0) dailyWage = 0;
          if (dailyWage > 100000) dailyWage = 100000;
          const totalCost = dailyWage * WORKING_DAYS;
          const piecesPerDay =
            WORKING_DAYS > 0 ? GRAND_TOTAL / WORKING_DAYS : 0;
          let costPerPiece = 0,
            costDisplay = "—",
            piecesPerDayDisplay = "—";
          if (GRAND_TOTAL > 0) {
            costPerPiece = totalCost / GRAND_TOTAL;
            costDisplay = `₹${formatIndianRupee(costPerPiece, 2)}`;
            piecesPerDayDisplay = formatIndianRupee(piecesPerDay, 1);
          }
          perDayCostSpan.innerText = `₹${formatIndianRupee(dailyWage)}`;
          totalWageCostSpan.innerText = `₹${formatIndianRupee(totalCost)}`;
          piecesPerDaySpan.innerText = piecesPerDayDisplay;
          document.getElementById("workDaysDisplay").innerText = WORKING_DAYS;
          if (costPerPiece !== lastCostPerPiece) {
            costBox.classList.add("highlight-update");
            setTimeout(() => costBox.classList.remove("highlight-update"), 300);
            lastCostPerPiece = costPerPiece;
          }
          costPerPieceSpan.innerText = costDisplay;
        }

        updateWageAndProductivity();
        dailyWageInput.addEventListener("input", updateWageAndProductivity);

        // Charts
        function formatNumber(num) {
          return num.toLocaleString("en-IN");
        }
        function updateProductMetrics(data) {
          const points = data[0].points;
          const total = points.reduce((sum, p) => sum + p.y, 0);
          document.getElementById("totalItemsBadge").innerHTML =
            `${formatNumber(total)} total pcs`;
          const sorted = [...points].sort((a, b) => b.y - a.y);
          let metricsHtml = "";
          if (sorted.length > 0) {
            metricsHtml += `<div class="metric-card"><div class="metric-icon"><i class="fas fa-crown"></i></div><div class="metric-content"><span class="metric-label">Top product</span><span class="metric-value">${sorted[0].name} <small>${formatNumber(sorted[0].y)} pcs</small></span></div></div>`;
          }
          const avg = (total / points.length).toFixed(1);
          metricsHtml += `<div class="metric-card"><div class="metric-icon"><i class="fas fa-chart-line"></i></div><div class="metric-content"><span class="metric-label">Average</span><span class="metric-value">${formatNumber(avg)} <small>pcs</small></span></div></div>
            <div class="metric-card"><div class="metric-icon"><i class="fas fa-tag"></i></div><div class="metric-content"><span class="metric-label">Products</span><span class="metric-value">${points.length} <small>types</small></span></div></div>`;
          document.getElementById("productMetrics").innerHTML = metricsHtml;
        }

        const productDataPoints = sortedProducts.map((name) => ({
          name,
          y: productTotals[name],
        }));
        const productSeries = [
          {
            name: "Products",
            points: productDataPoints.map((p) => ({ name: p.name, y: p.y })),
          },
        ];
        var productChart = JSC.chart("productChart", {
          legend_position: "inside left bottom",
          defaultSeries: { type: "pie", pointSelection: true },
          defaultPoint_label: {
            text: "<b>%name</b><br>%yValue pcs",
            placement: "auto",
            autoHide: false,
            style: { fontSize: "12px", fontWeight: "500", color: "#1e3a6b" },
          },
          defaultTooltip: {
            label_text: "<b>%name</b><br>Quantity: %yValue pcs",
            style: { fontSize: "13px" },
          },
          toolbar_items: {
            Mode: {
              margin: 10,
              type: "select",
              events_change: function (val) {
                productChart.options({
                  defaultPoint: { label: { placement: val } },
                });
              },
              items: "enum_placement",
            },
            "Auto Hide": {
              type: "checkbox",
              events_change: function (val) {
                productChart.options({
                  defaultPoint: { label: { autoHide: val } },
                });
              },
            },
          },
          title_label_text: "Product Distribution",
          yAxis: { label_text: "Quantity", formatString: "n" },
          series: productSeries,
        });
        updateProductMetrics(productSeries);

        const select = document.getElementById("productSelect");
        sortedProducts.forEach((prod) => {
          const opt = document.createElement("option");
          opt.value = prod;
          opt.textContent = prod;
          select.appendChild(opt);
        });

        let cutChart = null;
        const selectedSpan = document.getElementById("selectedProductName");
        const cutChartDiv = document.getElementById("cutChart");
        const cutEmptyMessage = document.getElementById("cutChartEmptyMessage");

        function updateCutPie(productKey) {
          const cuts = productCutDetails[productKey];
          if (!cuts || Object.keys(cuts).length === 0) {
            cutChartDiv.style.display = "none";
            cutEmptyMessage.style.display = "block";
            selectedSpan.innerText = productKey || "—";
            return;
          }
          cutChartDiv.style.display = "block";
          cutEmptyMessage.style.display = "none";
          const cutData = Object.keys(cuts).map((label) => ({
            name: label,
            y: cuts[label],
          }));
          if (cutChart) {
            cutChart.options({
              series: [
                {
                  name: "Distribution",
                  points: cutData.map((p) => ({ name: p.name, y: p.y })),
                },
              ],
              title_label_text: `${productKey} - Cut Distribution`,
            });
          } else {
            cutChart = JSC.chart("cutChart", {
              legend_position: "inside left bottom",
              defaultSeries: { type: "pie", pointSelection: true },
              defaultPoint_label: {
                text: "<b>%name</b><br>%yValue pcs",
                placement: "auto",
                autoHide: false,
              },
              toolbar_items: {
                Mode: {
                  margin: 10,
                  type: "select",
                  events_change: function (val) {
                    cutChart.options({
                      defaultPoint: { label: { placement: val } },
                    });
                  },
                  items: "enum_placement",
                },
                "Auto Hide": {
                  type: "checkbox",
                  events_change: function (val) {
                    cutChart.options({
                      defaultPoint: { label: { autoHide: val } },
                    });
                  },
                },
              },
              title_label_text: `${productKey} - Cut Distribution`,
              yAxis: { label_text: "Quantity", formatString: "n" },
              series: [
                {
                  name: "Distribution",
                  points: cutData.map((p) => ({ name: p.name, y: p.y })),
                },
              ],
            });
          }
          selectedSpan.innerText = productKey;
        }
        // Add this after your existing chart variables
let cutterChart = null;
const cutterChartDiv = document.getElementById("cutterChart");
const cutterEmptyMessage = document.getElementById("cutterChartEmptyMessage");

// Function to update cutter pie chart
function updateCutterPie(productKey) {
  // Filter entries based on selected product
  const filteredEntries = productKey === "All"
    ? tres
    : tres.filter(e => e.product.trim() === productKey);

  // Group by cutter
  const cutterMap = new Map();

  filteredEntries.forEach(entry => {
    // Only count production entries (you can adjust this condition)
    if (!entry.given_to) {  // Count only entries not given to someone
      const cutter = entry.cutter || "Unknown";
      const currentTotal = cutterMap.get(cutter) || 0;
      cutterMap.set(cutter, currentTotal + entry.pieces);
    }
  });

  // Convert to chart data format
  const cutterData = Array.from(cutterMap.entries())
    .map(([name, pieces]) => ({
      name: name,
      y: pieces
    }))
    .sort((a, b) => b.y - a.y); // Sort by pieces descending

  if (cutterData.length === 0) {
    cutterChartDiv.style.display = "none";
    cutterEmptyMessage.style.display = "block";
    return;
  }

  cutterChartDiv.style.display = "block";
  cutterEmptyMessage.style.display = "none";

  if (cutterChart) {
    cutterChart.options({
      series: [{
        name: "Cutters",
        points: cutterData
      }],
      title_label_text: productKey === "All"
        ? "Cutter Distribution - All Products"
        : `Cutter Distribution - ${productKey}`
    });
  } else {
    cutterChart = JSC.chart("cutterChart", {
      legend_position: "inside left bottom",
      defaultSeries: {
        type: "pie",
        pointSelection: true
      },
      defaultPoint_label: {
        text: "<b>%name</b><br>%yValue pcs<br>%percentOfSeries%",
        placement: "auto",
        autoHide: false,
        style: { fontSize: "12px", fontWeight: "500", color: "#1e3a6b" }
      },
      defaultTooltip: {
        label_text: "<b>%name</b><br>Pieces: %yValue<br>Share: %percentOfSeries%",
        style: { fontSize: "13px" }
      },
      toolbar_items: {
        Mode: {
          margin: 10,
          type: "select",
          events_change: function (val) {
            cutterChart.options({
              defaultPoint: { label: { placement: val } }
            });
          },
          items: "enum_placement",
        },
        "Auto Hide": {
          type: "checkbox",
          events_change: function (val) {
            cutterChart.options({
              defaultPoint: { label: { autoHide: val } }
            });
          },
        },
      },
      title_label_text: productKey === "All"
        ? "Cutter Distribution - All Products"
        : `Cutter Distribution - ${productKey}`,
      yAxis: {
        label_text: "Pieces",
        formatString: "n"
      },
      series: [{
        name: "Cutters",
        points: cutterData
      }]
    });
  }
}

// Add metrics for cutters (optional)
function updateCutterMetrics() {
  const cutterMetricsDiv = document.getElementById("cutterMetrics");
  if (!cutterMetricsDiv) {
    // Create metrics div if it doesn't exist
    const metricsRow = document.createElement("div");
    metricsRow.className = "metrics-row";
    metricsRow.id = "cutterMetrics";
    document.querySelector("#cutterChart").parentNode.appendChild(metricsRow);
  }

  const cutterMap = new Map();
  tres.forEach(entry => {
    if (!entry.given_to) {
      const cutter = entry.cutter || "Unknown";
      cutterMap.set(cutter, (cutterMap.get(cutter) || 0) + entry.pieces);
    }
  });

  const cutterData = Array.from(cutterMap.entries())
    .map(([name, pieces]) => ({ name, pieces }))
    .sort((a, b) => b.pieces - a.pieces);

  let metricsHtml = "";

  if (cutterData.length > 0) {
    // Top cutter
    metricsHtml += `
      <div class="metric-card">
        <div class="metric-icon"><i class="fas fa-crown"></i></div>
        <div class="metric-content">
          <span class="metric-label">Top cutter</span>
          <span class="metric-value">${cutterData[0].name} <small>${formatNumber(cutterData[0].pieces)} pcs</small></span>
        </div>
      </div>
    `;

    // Average per cutter
    const avg = (cutterData.reduce((sum, c) => sum + c.pieces, 0) / cutterData.length).toFixed(1);
    metricsHtml += `
      <div class="metric-card">
        <div class="metric-icon"><i class="fas fa-chart-line"></i></div>
        <div class="metric-content">
          <span class="metric-label">Average</span>
          <span class="metric-value">${formatNumber(avg)} <small>pcs</small></span>
        </div>
      </div>
    `;

    // Total cutters
    metricsHtml += `
      <div class="metric-card">
        <div class="metric-icon"><i class="fas fa-users"></i></div>
        <div class="metric-content">
          <span class="metric-label">Total cutters</span>
          <span class="metric-value">${cutterData.length} <small>people</small></span>
        </div>
      </div>
    `;
  }

  document.getElementById("cutterMetrics").innerHTML = metricsHtml;
}

// Update the product select change handler to also update cutter chart
const originalChangeHandler = select.onchange;
select.addEventListener("change", (e) => {
  const product = e.target.value;
  updateCutPie(product);
  updateCutterPie(product); // Add this line
});

// Also update when switching to All Products or when page loads
// Initialize cutter chart
if (sortedProducts.length > 0) {
  updateCutterPie(sortedProducts[0]); // For specific product
} else {
  updateCutterPie("All"); // Fallback to All
}
updateCutterMetrics();

// If you have a global "All Products" option, make sure to handle it
// You might want to add an "All Products" option to your product select
const allOption = document.createElement("option");
allOption.value = "All";
allOption.textContent = "All Products";
select.insertBefore(allOption, select.firstChild);
      function updateGroupedDailyBar() {
  const dailyProductMap = new Map();
  tres.forEach((entry) => {
    // FIX: Include all entries for daily production chart
    // Show both production and given items to track daily activity
    const dateStr = entry.entry_datetime.toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
    });
    const product = entry.product.trim();
    if (!dailyProductMap.has(dateStr)) dailyProductMap.set(dateStr, {});
    const dayData = dailyProductMap.get(dateStr);
    dayData[product] = (dayData[product] || 0) + entry.pieces;
  });
  const allProducts = [
    ...new Set(tres.map((e) => e.product.trim())),
  ].sort();
  const sortedDates = Array.from(dailyProductMap.keys()).sort((a, b) =>
    a.localeCompare(b, undefined, { numeric: true }),
  );
  const series = allProducts.map((product) => ({
    name: product,
    points: sortedDates.map((date) => ({
      name: date,
      y: (dailyProductMap.get(date) || {})[product] || 0,
    })),
  }));
  if (dailyBarChart) {
    dailyBarChart.options({ series });
  } else {
    dailyBarChart = JSC.chart("dailyGroupBarChart", {
      type: "column",
      title_label_text: "Daily production by product",
      xAxis: { label_text: "Date" },
      yAxis: { label_text: "Pieces" },
      series: series,
      toolbar_visible: false,
      legend_visible: true,
    });
  }
  document.getElementById("dailyBarEmptyMessage").style.display = "none";
}

        let dailyBarChart = null;
        updateGroupedDailyBar();

        if (sortedProducts.length > 0) {
          updateCutPie(sortedProducts[0]);
          select.value = sortedProducts[0];
        }
        select.addEventListener("change", (e) => updateCutPie(e.target.value));

        // ------------------------------------------------------------------
        // SUPPLIER/LOT/BALE VIEW (hierarchical with backend data display)
        // ------------------------------------------------------------------
        const lumpData = tres.filter((e) => e.lump_id);

        // Build hierarchical data structure
        const supplierMap = new Map();
        lumpData.forEach((entry) => {
          if (!supplierMap.has(entry.supplier)) {
            supplierMap.set(entry.supplier, new Map());
          }
          const lotMap = supplierMap.get(entry.supplier);
          if (!lotMap.has(entry.lot_number)) {
            lotMap.set(entry.lot_number, new Map());
          }
          const baleMap = lotMap.get(entry.lot_number);
          if (!baleMap.has(entry.bale_number)) {
            baleMap.set(entry.bale_number, {
              bale_number: entry.bale_number,
              packing_date: entry.packing_date,
              packing_slip: `SLIP-${entry.supplier.slice(0, 3)}${entry.bale_number}`,
              lumps: new Map(),
            });
          }
          const bale = baleMap.get(entry.bale_number);
          if (!bale.lumps.has(entry.lump_id)) {
            bale.lumps.set(entry.lump_id, {
              lump_id: entry.lump_id,
              product: entry.product,
              color: entry.type_B,
              meter: entry.meter,
              entries: [],
              totalPieces: 0,
              totalKg: 0,
              meterPerPiece: 1.97, // default
            });
          }
          const lump = bale.lumps.get(entry.lump_id);
          lump.entries.push(entry);
          lump.totalPieces += entry.pieces;
          lump.totalKg += entry.kg;
        });

        // Populate product select
        const products = [...new Set(lumpData.map((e) => e.product))].sort();
        const globalProductSelect = document.getElementById(
          "globalProductSelect",
        );
        products.forEach((p) => globalProductSelect.add(new Option(p, p)));

        const supplierHierarchy = document.getElementById("supplierHierarchy");
        const supplierRowState = {};

        function renderSupplierHierarchy() {
          supplierHierarchy.innerHTML = "";
          let totalClothAll = 0,
            totalWasteAll = 0;
          const selectedProduct = globalProductSelect.value;

          Array.from(supplierMap.entries()).forEach(([supplier, lotMap]) => {
            const supplierDiv = document.createElement("div");
            supplierDiv.className = "supplier-card";

            // Supplier header
            const suppHeader = document.createElement("div");
            suppHeader.className = "supplier-header";
            suppHeader.innerHTML = `
                    <i class="fas fa-building"></i>
                    <h3>${supplier}</h3>
                    <span class="collapse-icon"><i class="fas fa-chevron-down"></i></span>
                `;
            supplierDiv.appendChild(suppHeader);

            const supplierContent = document.createElement("div");
            supplierContent.className = "supplier-content";

            const lotGrid = document.createElement("div");
            lotGrid.className = "lot-grid";

            Array.from(lotMap.entries()).forEach(([lotNumber, baleMap]) => {
              const lotDiv = document.createElement("div");
              lotDiv.className = "lot-card";

              // Lot header
              const lotHeader = document.createElement("div");
              lotHeader.className = "lot-header";
              lotHeader.innerHTML = `
                        <i class="fas fa-scroll"></i>
                        <h4>Lot ${lotNumber}</h4>
                        <span class="lot-badge">${baleMap.size} bales</span>
                    `;
              lotDiv.appendChild(lotHeader);

              // Lot summary (dynamic)
              const lotSummary = document.createElement("div");
              lotSummary.className = "lot-summary";

              // Calculate lot totals
              let lotPieces = 0,
                lotKg = 0,
                lotMeter = 0,
                lotCloth = 0;
              const packingDates = new Set();
              const slips = [];

              baleMap.forEach((bale) => {
                packingDates.add(bale.packing_date);
                slips.push(bale.packing_slip);
                bale.lumps.forEach((lump) => {
                  if (
                    selectedProduct === "All" ||
                    lump.product === selectedProduct
                  ) {
                    const cloth = lump.meterPerPiece * lump.totalPieces;
                    const waste = Math.max(0, lump.meter - cloth);
                    lotPieces += lump.totalPieces;
                    lotKg += lump.totalKg;
                    lotMeter += lump.meter;
                    lotCloth += cloth;
                  }
                });
              });

              const avgCloth =
                lotPieces > 0 ? (lotCloth / lotPieces).toFixed(2) : "0";
              const avgWaste =
                lotPieces > 0
                  ? ((lotMeter - lotCloth) / lotPieces).toFixed(2)
                  : "0";
              const avgKg =
                lotPieces > 0 ? (lotKg / lotPieces).toFixed(2) : "0";

              lotSummary.innerHTML = `
                        <span><i class="fas fa-boxes"></i> Bales: ${baleMap.size}</span>
                        <span><i class="fas fa-calendar-check"></i> ${Array.from(packingDates).join(", ")}</span>
                        <span><i class="fas fa-tag"></i> ${slips.join(", ")}</span>
                        <span><i class="fas fa-ruler"></i> Avg cloth: <span class="avg-value">${avgCloth}</span> m</span>
                        <span><i class="fas fa-trash-alt"></i> Avg waste: <span class="avg-value">${avgWaste}</span> m</span>
                        <span><i class="fas fa-weight-hanging"></i> Avg kg: <span class="avg-value">${avgKg}</span></span>
                        <span><i class="fas fa-cubes"></i> Total pcs: <span class="avg-value">${lotPieces}</span></span>
                    `;
              lotDiv.appendChild(lotSummary);

              const lotContent = document.createElement("div");
              lotContent.className = "lot-content";

              const baleGrid = document.createElement("div");
              baleGrid.className = "bale-grid";

              baleMap.forEach((bale) => {
                const baleDiv = document.createElement("div");
                baleDiv.className = "bale-card";

                // Bale title
                const baleTitle = document.createElement("div");
                baleTitle.className = "bale-title";
                baleTitle.innerHTML = `
                            <span class="bale-no">Bale #${bale.bale_number}</span>
                            <span class="packing-date"><i class="far fa-calendar"></i> ${bale.packing_date}</span>
                            <span class="packing-slip"><i class="fas fa-receipt"></i> ${bale.packing_slip}</span>
                        `;
                baleDiv.appendChild(baleTitle);

                // Bale stats
                let baleLumps = 0,
                  baleBundles = 0,
                  baleCloth = 0,
                  baleWaste = 0;
                bale.lumps.forEach((lump) => {
                  if (
                    selectedProduct === "All" ||
                    lump.product === selectedProduct
                  ) {
                    baleLumps++;
                    baleBundles += lump.entries.length;
                    const cloth = lump.meterPerPiece * lump.totalPieces;
                    const waste = Math.max(0, lump.meter - cloth);
                    baleCloth += cloth;
                    baleWaste += waste;
                    totalClothAll += cloth;
                    totalWasteAll += waste;
                  }
                });

                const baleStats = document.createElement("div");
                baleStats.className = "bale-stats";
                baleStats.innerHTML = `
                            <div class="bale-stat-item"><i class="fas fa-cubes"></i> Lumps: <span class="val">${baleLumps}</span></div>
                            <div class="bale-stat-item"><i class="fas fa-cut"></i> Bundles: <span class="val">${baleBundles}</span></div>
                            <div class="bale-stat-item"><i class="fas fa-ruler"></i> Cloth: <span class="val">${baleCloth.toFixed(2)}</span> m</div>
                            <div class="bale-stat-item"><i class="fas fa-trash-alt"></i> Waste: <span class="val">${baleWaste.toFixed(2)}</span> m</div>
                        `;
                baleDiv.appendChild(baleStats);

                // Lumps
                bale.lumps.forEach((lump) => {
                  if (
                    selectedProduct !== "All" &&
                    lump.product !== selectedProduct
                  )
                    return;

                  const lumpDiv = document.createElement("div");
                  lumpDiv.className = "lump-item";

                  const lumpHeader = document.createElement("div");
                  lumpHeader.className = "lump-header";
                  lumpHeader.innerHTML = `
                                <span class="lump-name"><i class="fas fa-cube"></i> Lump ${lump.lump_id} · ${lump.color}</span>
                                <span style="font-size:0.8rem; background:#ecf3fa; padding:0.2rem 1rem; border-radius:30px;">${lump.entries[0].entry_datetime.toLocaleDateString("en-IN")}</span>
                            `;
                  lumpDiv.appendChild(lumpHeader);

                  // Backend data display (static, never changes)
                  const backendDataDiv = document.createElement("div");
                  backendDataDiv.className = "lump-backend-data";
                  backendDataDiv.innerHTML = `
                                <div class="backend-item"><span class="label">Lumps:</span> <span class="value">1</span></div>
                                <div class="backend-item"><span class="label">Bundles:</span> <span class="value">${lump.entries.length}</span></div>
                                <div class="backend-item"><span class="label">Cloth (fixed):</span> <span class="value">${(lump.meterPerPiece * lump.totalPieces).toFixed(2)}</span> m</div>
                                <div class="backend-item"><span class="label">Waste (fixed):</span> <span class="value">${Math.max(0, lump.meter - lump.meterPerPiece * lump.totalPieces).toFixed(2)}</span> m</div>
                                <div class="backend-item"><span class="label">Original Meter:</span> <span class="value">${lump.meter}</span> m</div>
                            `;
                  lumpDiv.appendChild(backendDataDiv);

                  const meterRow = document.createElement("div");
                  meterRow.className = "meter-row";

                  const cloth = lump.meterPerPiece * lump.totalPieces;
                  const waste = Math.max(0, lump.meter - cloth);
                  const avgKg =
                    lump.totalPieces > 0
                      ? (lump.totalKg / lump.totalPieces).toFixed(2)
                      : 0;

                  meterRow.innerHTML = `
                                <div class="meter-input-group">
                                    <label>m/pc:</label>
                                    <input type="number" step="0.01" min="0" value="${lump.meterPerPiece}" class="lump-meter-input" data-supplier="${supplier}" data-lot="${lotNumber}" data-bale="${bale.bale_number}" data-lump="${lump.lump_id}">
                                </div>
                                <div class="lump-stats">
                                    <div class="stat-pill"><span class="small">cloth</span><span class="big">${cloth.toFixed(2)}</span></div>
                                    <div class="stat-pill"><span class="small">waste</span><span class="big">${waste.toFixed(2)}</span></div>
                                    <div class="stat-pill"><span class="small">avg kg</span><span class="big">${avgKg}</span></div>
                                </div>
                            `;
                  lumpDiv.appendChild(meterRow);

                  // Bundle table
                  const table = document.createElement("table");
table.className = "bundle-table";
table.innerHTML = `
              <thead><tr><th>ID</th><th>Pcs</th><th>Kg</th><th>Cutter</th><th>Status</th><th>To</th></tr></thead>
              <tbody>
                  ${lump.entries
                    .map(
                      (e) => `<tr>
                      <td>#${e.id}</td>
                      <td>${e.pieces}</td>
                      <td>${e.kg}</td>
                      <td>${e.cutter || "—"}</td>
                      <td><span class="status-badge">${e.status}</span></td>
                      <td>${e.given_to || "—"}</td>
                  </tr>`,
                    )
                    .join("")}
              </tbody>
          `;
                  lumpDiv.appendChild(table);
                  baleDiv.appendChild(lumpDiv);
                });

                baleGrid.appendChild(baleDiv);
              });

              lotContent.appendChild(baleGrid);
              lotDiv.appendChild(lotContent);
              lotGrid.appendChild(lotDiv);

              // Toggle lot
              lotHeader.addEventListener("click", (e) => {
                e.stopPropagation();
                lotDiv.classList.toggle("collapsed");
              });
            });

            supplierContent.appendChild(lotGrid);
            supplierDiv.appendChild(supplierContent);
            supplierHierarchy.appendChild(supplierDiv);

            // Toggle supplier
            suppHeader.addEventListener("click", (e) => {
              e.stopPropagation();
              supplierDiv.classList.toggle("collapsed");
            });
          });

          document.getElementById("totalClothUsed").innerText =
            totalClothAll.toFixed(2);
          document.getElementById("totalWaste").innerText =
            totalWasteAll.toFixed(2);

          // Update global stats
          updateGlobalStats();
        }

        function updateGlobalStats() {
          const selectedProduct = globalProductSelect.value;
          let totalPieces = 0,
            totalKg = 0,
            totalMeter = 0,
            totalWaste = 0;

          supplierMap.forEach((lotMap, supplier) => {
            lotMap.forEach((baleMap, lot) => {
              baleMap.forEach((bale) => {
                bale.lumps.forEach((lump) => {
                  if (
                    selectedProduct === "All" ||
                    lump.product === selectedProduct
                  ) {
                    totalPieces += lump.totalPieces;
                    totalKg += lump.totalKg;
                    totalMeter += lump.meter;
                    const cloth = lump.meterPerPiece * lump.totalPieces;
                    totalWaste += Math.max(0, lump.meter - cloth);
                  }
                });
              });
            });
          });

          const avgKg =
            totalPieces > 0 ? (totalKg / totalPieces).toFixed(2) : "0.00";
          const wastePct =
            totalMeter > 0
              ? ((totalWaste / totalMeter) * 100).toFixed(1)
              : "0.0";

          document.getElementById("globalAvgKg").innerText = avgKg;
          document.getElementById("globalWastagePct").innerText = wastePct;
        }

        // Meter input listener - use event delegation to prevent page jump
        document.addEventListener("input", function (e) {
          if (e.target.classList.contains("lump-meter-input")) {
            // Prevent default behavior that might cause page jump
            e.preventDefault();

            const supplier = e.target.dataset.supplier;
            const lot = e.target.dataset.lot;
            const baleNum = parseInt(e.target.dataset.bale);
            const lumpId = parseInt(e.target.dataset.lump);
            const val = parseFloat(e.target.value) || 0;

            const lump = supplierMap
              .get(supplier)
              ?.get(lot)
              ?.get(baleNum)
              ?.lumps.get(lumpId);
            if (lump) {
              lump.meterPerPiece = val;
              // Use requestAnimationFrame to batch updates and prevent layout thrashing
              requestAnimationFrame(() => {
                renderSupplierHierarchy();
              });
            }
          }
        });

        // Global product meter
        globalProductSelect.addEventListener("change", renderSupplierHierarchy);
        document
          .getElementById("globalMeterPerPiece")
          .addEventListener("input", function (e) {
            e.preventDefault();
            const globalVal = parseFloat(e.target.value) || 0;
            const selectedProduct = globalProductSelect.value;

            supplierMap.forEach((lotMap, supplier) => {
              lotMap.forEach((baleMap, lot) => {
                baleMap.forEach((bale) => {
                  bale.lumps.forEach((lump) => {
                    if (
                      selectedProduct === "All" ||
                      lump.product === selectedProduct
                    ) {
                      lump.meterPerPiece = globalVal;
                    }
                  });
                });
              });
            });

            requestAnimationFrame(() => {
              renderSupplierHierarchy();
            });
          });

        // View toggle
        document
          .getElementById("showProductionView")
          .addEventListener("click", function () {
            document
              .getElementById("productionView")
              .classList.remove("hidden");
            document.getElementById("lumpView").classList.add("hidden");
            this.classList.add("active");
            document.getElementById("showLumpView").classList.remove("active");
          });

        document
          .getElementById("showLumpView")
          .addEventListener("click", function () {
            document.getElementById("productionView").classList.add("hidden");
            document.getElementById("lumpView").classList.remove("hidden");
            this.classList.add("active");
            document
              .getElementById("showProductionView")
              .classList.remove("active");
            renderSupplierHierarchy();
          });

        // Initial render
        renderSupplierHierarchy();
        updateGlobalStats();
      })();