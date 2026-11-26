(function () {
  "use strict";

  const ICONS = {
    alert:
      '<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M12 3L2 21h20L12 3z"></path><line x1="12" y1="9" x2="12" y2="14"></line><circle cx="12" cy="17.5" r="0.9" fill="currentColor"></circle></svg>',
    info:
      '<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><line x1="12" y1="11" x2="12" y2="16"></line><circle cx="12" cy="8" r="0.9" fill="currentColor"></circle></svg>',
    external:
      '<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>'
  };

  const STRUCT_RATES_YEN_PER_TSUBO = {
    wood_normal: { label: "木造（標準重機）", perTsubo: 50000, sundryFixed: 250000 },
    wood_narrow: { label: "木造（狭小道路・手壊し併用）", perTsubo: 68000, sundryFixed: 350000 },
    steel: { label: "鉄骨造", perTsubo: 65000, sundryFixed: 320000 },
    rc: { label: "RC（鉄筋コンクリート）造", perTsubo: 85000, sundryFixed: 450000 }
  };

  const PRESETS = {
    rural: {
      landEvalMan: 600,
      landAreaSqm: 220,
      bldgEvalMan: 100,
      bldgTsubo: 32,
      struct: "wood_normal",
      upkeepMan: 14,
      buyoutRatio: 45
    },
    regional: {
      landEvalMan: 1200,
      landAreaSqm: 180,
      bldgEvalMan: 150,
      bldgTsubo: 30,
      struct: "wood_normal",
      upkeepMan: 14,
      buyoutRatio: 55
    },
    suburban: {
      landEvalMan: 2400,
      landAreaSqm: 140,
      bldgEvalMan: 180,
      bldgTsubo: 28,
      struct: "wood_narrow",
      upkeepMan: 16,
      buyoutRatio: 68
    }
  };

  let allMunicipalities = [];
  let affiliatePrograms = {};
  let disclosureLabel = "PR・広告提携枠";
  let selectedMuniCode = "13112";

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatManYen(yen, withSign) {
    const man = Math.round(yen / 10000);
    const absStr = Math.abs(man).toLocaleString("ja-JP") + "万円";
    if (man < 0) {
      return "▲" + absStr;
    }
    if (withSign && man > 0) {
      return "+" + absStr;
    }
    return absStr;
  }

  function formatExactYen(yen) {
    return Math.round(yen).toLocaleString("ja-JP") + "円";
  }

  function computePropertyTaxes(landEvalYen, landAreaSqm, bldgEvalYen, cityPlanTaxRate) {
    const fixedRate = 0.014;
    const smallRatio = Math.min(1, 200 / Math.max(1, landAreaSqm));
    const generalRatio = 1 - smallRatio;

    const smallEval = landEvalYen * smallRatio;
    const generalEval = landEvalYen * generalRatio;

    const landFixedSpecial = (smallEval * (1 / 6) + generalEval * (1 / 3)) * fixedRate;
    const landPlanSpecial = (smallEval * (1 / 3) + generalEval * (2 / 3)) * cityPlanTaxRate;
    const landTaxWithException = landFixedSpecial + landPlanSpecial;

    const taxableBareLand = landEvalYen * 0.70;
    const landTaxRevoked = taxableBareLand * (fixedRate + cityPlanTaxRate);

    const bldgTax = bldgEvalYen * (fixedRate + cityPlanTaxRate);

    return {
      landTaxWithException: Math.round(landTaxWithException),
      landTaxRevoked: Math.round(landTaxRevoked),
      bldgTax: Math.round(bldgTax),
      jumpRatio: landTaxWithException > 0 ? landTaxRevoked / landTaxWithException : 4.2
    };
  }

  function renderSvgChart(seriesA, seriesB, seriesC) {
    const width = 620;
    const height = 236;
    const padLeft = 72;
    const padRight = 20;
    const padTop = 18;
    const padBottom = 32;

    const allVals = [0].concat(seriesA, seriesB, seriesC);
    const maxVal = Math.max.apply(null, allVals) * 1.1 + 500000;
    const minVal = Math.min.apply(null, allVals) * 1.1 - 500000;
    const span = Math.max(1, maxVal - minVal);

    function xPos(yearIndex) {
      return padLeft + ((width - padLeft - padRight) * yearIndex) / 9;
    }

    function yPos(val) {
      return padTop + ((maxVal - val) / span) * (height - padTop - padBottom);
    }

    function buildPolyline(arr, color) {
      const pts = arr
        .map(function (v, idx) {
          return xPos(idx).toFixed(1) + "," + yPos(v).toFixed(1);
        })
        .join(" ");
      const dots = arr
        .map(function (v, idx) {
          return (
            '<circle cx="' +
            xPos(idx).toFixed(1) +
            '" cy="' +
            yPos(v).toFixed(1) +
            '" r="3" fill="' +
            color +
            '" />'
          );
        })
        .join("");
      return (
        '<polyline fill="none" stroke="' +
        color +
        '" stroke-width="2" points="' +
        pts +
        '" />' +
        dots
      );
    }

    const zeroY = yPos(0);
    let gridLines = "";
    for (let step = 0; step <= 4; step++) {
      const val = minVal + (span * step) / 4;
      const y = yPos(val);
      gridLines +=
        '<line x1="' +
        padLeft +
        '" y1="' +
        y.toFixed(1) +
        '" x2="' +
        (width - padRight) +
        '" y2="' +
        y.toFixed(1) +
        '" stroke="#EEF0F4" stroke-width="1" />' +
        '<text x="' +
        (padLeft - 8) +
        '" y="' +
        (y + 4).toFixed(1) +
        '" text-anchor="end" font-size="11" font-weight="500" fill="#64748B">' +
        formatManYen(val, false) +
        "</text>";
    }

    let xLabels = "";
    for (let i = 0; i < 10; i++) {
      xLabels +=
        '<text x="' +
        xPos(i).toFixed(1) +
        '" y="' +
        (height - 8) +
        '" text-anchor="middle" font-size="11" font-weight="500" fill="#64748B">' +
        (i + 1) +
        "年</text>";
    }

    return (
      '<svg viewBox="0 0 ' +
      width +
      " " +
      height +
      '" width="100%" height="auto" role="img" aria-label="10年間累計収支比較グラフ">' +
      gridLines +
      '<line x1="' +
      padLeft +
      '" y1="' +
      zeroY.toFixed(1) +
      '" x2="' +
      (width - padRight) +
      '" y2="' +
      zeroY.toFixed(1) +
      '" stroke="#94A3B8" stroke-width="1" stroke-dasharray="4 3" />' +
      buildPolyline(seriesC, "#15803D") +
      buildPolyline(seriesA, "#B45309") +
      buildPolyline(seriesB, "#DC2626") +
      xLabels +
      "</svg>"
    );
  }

  function recalculate() {
    const muni = allMunicipalities.find(function (m) {
      return m.municipality_code === selectedMuniCode;
    });

    const landEvalYen = Math.max(0, Number(document.getElementById("land-eval-man").value) || 0) * 10000;
    const landAreaSqm = Math.max(20, Number(document.getElementById("land-area-sqm").value) || 180);
    const bldgEvalYen = Math.max(0, Number(document.getElementById("bldg-eval-man").value) || 0) * 10000;
    const bldgTsubo = Math.max(8, Number(document.getElementById("bldg-tsubo").value) || 30);
    const structKey = document.getElementById("bldg-struct").value;
    const upkeepYen = Math.max(0, Number(document.getElementById("upkeep-man").value) || 0) * 10000;
    const rawSubsidyYen = Math.max(0, Number(document.getElementById("subsidy-override-man").value) || 0) * 10000;
    const kanriRisk = document.getElementById("kanri-risk-select").value;
    const cityPlanRate = Number(document.getElementById("city-plan-tax").value) || 0;
    const buyoutRatioPct = Math.max(5, Number(document.getElementById("buyout-ratio").value) || 55);

    const structInfo = STRUCT_RATES_YEN_PER_TSUBO[structKey] || STRUCT_RATES_YEN_PER_TSUBO.wood_normal;
    const grossDemolitionYen = bldgTsubo * structInfo.perTsubo + structInfo.sundryFixed;
    const appliedSubsidyYen = Math.min(rawSubsidyYen, Math.floor(grossDemolitionYen * 0.8));
    const netDemolitionYen = Math.max(0, grossDemolitionYen - appliedSubsidyYen);

    const taxes = computePropertyTaxes(landEvalYen, landAreaSqm, bldgEvalYen, cityPlanRate);
    const estimatedBuyoutYen = Math.round(landEvalYen * (buyoutRatioPct / 100));

    const seriesA = [];
    const seriesB = [];
    const seriesC = [];

    let cumA = 0;
    let cumB = 0;

    for (let year = 1; year <= 10; year++) {
      const isRevokedByWarning = kanriRisk === "warn_y3" && year >= 3;
      const annualLandTaxA = isRevokedByWarning ? taxes.landTaxRevoked : taxes.landTaxWithException;
      const extraPestRepairA = isRevokedByWarning ? 60000 : 0;
      cumA -= annualLandTaxA + taxes.bldgTax + upkeepYen + extraPestRepairA;
      seriesA.push(cumA);

      const year1DemoOutflow = year === 1 ? netDemolitionYen : 0;
      const annualBareLandUpkeep = 35000;
      const annualLandTaxB = year === 1 ? taxes.landTaxWithException : taxes.landTaxRevoked;
      cumB -= year1DemoOutflow + annualLandTaxB + annualBareLandUpkeep;
      seriesB.push(cumB);

      seriesC.push(estimatedBuyoutYen);
    }

    const total10YrA = seriesA[9];
    const total10YrB = seriesB[9];
    const total10YrC = seriesC[9];
    const advantageCvsB = total10YrC - total10YrB;
    const advantageCvsA = total10YrC - total10YrA;

    const headerPestLink = document.getElementById("header-pest-link");
    if (headerPestLink && muni) {
      headerPestLink.href = "./index.html?code=" + encodeURIComponent(muni.municipality_code);
    }

    document.getElementById("tax-jump-banner").innerHTML =
      '<div class="callout-title">' +
      ICONS.alert +
      "<span>住宅用地特例の解除で、土地の年税額が " +
      formatExactYen(taxes.landTaxWithException) +
      " → " +
      formatExactYen(taxes.landTaxRevoked) +
      "（約" +
      taxes.jumpRatio.toFixed(1) +
      "倍）に増えます</span></div>" +
      "<div>更地化や管理不全空家の勧告後は1/6特例が外れ、土地税だけで10年間に<strong>約" +
      formatManYen(taxes.landTaxRevoked * 9 + taxes.landTaxWithException, false) +
      "</strong>かかります。買い手が決まる前の先行解体には注意が必要です。</div>";

    document.getElementById("scenario-cards-container").innerHTML =
      '<div class="scenario-card">' +
      '<span class="scenario-tag">A. 空き家のまま保有</span>' +
      '<h3 class="scenario-title">10年間所有・維持</h3>' +
      '<div class="scenario-net negative">' +
      formatManYen(total10YrA, true) +
      "</div>" +
      '<ul class="scenario-detail-list">' +
      "<li>初年度税額: " +
      formatExactYen(taxes.landTaxWithException + taxes.bldgTax) +
      "/年</li>" +
      "<li>維持管理費: " +
      formatManYen(upkeepYen, false) +
      "/年</li>" +
      "<li>" +
      (kanriRisk === "warn_y3"
        ? "3年目勧告で土地税" + taxes.jumpRatio.toFixed(1) + "倍を反映"
        : "10年間特例維持と仮定") +
      "</li>" +
      "</ul></div>" +
      '<div class="scenario-card tax-shock">' +
      '<span class="scenario-tag">B. 先行解体＋更地保有</span>' +
      '<h3 class="scenario-title">補助金解体後に未売却</h3>' +
      '<div class="scenario-net negative">' +
      formatManYen(total10YrB, true) +
      "</div>" +
      '<ul class="scenario-detail-list">' +
      "<li>解体費総額: " +
      formatManYen(grossDemolitionYen, false) +
      "</li>" +
      "<li>自治体補助金: ▲" +
      formatManYen(appliedSubsidyYen, false) +
      "</li>" +
      "<li>2年目以降の更地税: " +
      formatExactYen(taxes.landTaxRevoked) +
      "/年</li>" +
      "</ul></div>" +
      '<div class="scenario-card best-choice">' +
      '<span class="scenario-tag">C. 解体せず現況買取</span>' +
      '<h3 class="scenario-title">訳あり専門買取で現金化</h3>' +
      '<div class="scenario-net positive">' +
      formatManYen(total10YrC, true) +
      "</div>" +
      '<ul class="scenario-detail-list">' +
      "<li>解体・残置物撤去・仲介料: 0円</li>" +
      "<li>翌年以降の税・管理費: 0円</li>" +
      "<li><strong>B案との10年収支差: +" +
      formatManYen(advantageCvsB, false) +
      "</strong></li>" +
      "</ul></div>";

    document.getElementById("cashflow-svg-holder").innerHTML = renderSvgChart(seriesA, seriesB, seriesC);

    const minRequiredLandSalePriceForB = estimatedBuyoutYen + netDemolitionYen + taxes.landTaxRevoked * 2;
    document.getElementById("decision-advice-box").innerHTML =
      '<div class="callout-title">' +
      ICONS.info +
      "<span>損益分岐の目安</span></div>" +
      "<div>" +
      "解体後の土地売却が有利になるのは、1〜2年以内に<strong>諸経費控除後 " +
      formatManYen(minRequiredLandSalePriceForB, false) +
      " 以上</strong>で確実に売れる人気エリアに限られます。シロアリ・雨漏り・家財残置がある物件や郊外立地では、先に" +
      formatManYen(netDemolitionYen, false) +
      "をかけて解体する前に<strong>現況のままの買取査定額</strong>を確認すると安全です（10年放置比で<strong>+" +
      formatManYen(advantageCvsA, false) +
      "</strong>改善）。" +
      "</div>";

    const kaitoriPartner = affiliatePrograms.akiya_kaitori;
    const kaitaiPartner = affiliatePrograms.akiya_kaitai;
    const shiroariPartner = affiliatePrograms.shiroari_110;
    let ctaBlock = "";
    if (kaitaiPartner || kaitoriPartner) {
      const primaryPartner = kaitaiPartner || kaitoriPartner;
      const primaryPixel = primaryPartner.impression_url
        ? '<img src="' +
          escapeHtml(primaryPartner.impression_url) +
          '" width="1" height="1" alt="" style="width:1px;height:1px;border:0;position:absolute;opacity:0;pointer-events:none;">'
        : "";
      const kaitoriSecondaryHtml =
        kaitaiPartner && kaitoriPartner
          ? '<a class="cta-btn-secondary" href="' +
            escapeHtml(kaitoriPartner.target_url) +
            '" target="_blank" rel="nofollow sponsored noopener">' +
            "<span>C案（現況売却）を検討中の方：" +
            escapeHtml(kaitoriPartner.cta_button_text) +
            "</span>" +
            ICONS.external +
            "</a>" +
            (kaitoriPartner.impression_url
              ? '<img src="' +
                escapeHtml(kaitoriPartner.impression_url) +
                '" width="1" height="1" alt="" style="width:1px;height:1px;border:0;position:absolute;opacity:0;pointer-events:none;">'
              : "")
          : "";
      const shiroariSecondaryHtml = shiroariPartner
        ? '<a class="cta-btn-secondary" href="' +
          escapeHtml(shiroariPartner.target_url) +
          '" target="_blank" rel="nofollow sponsored noopener">' +
          "<span>A案（保有・賃貸維持）の劣化予防：床下シロアリ無料点検（シロアリ110番）を見る</span>" +
          ICONS.external +
          "</a>" +
          (shiroariPartner.impression_url
            ? '<img src="' +
              escapeHtml(shiroariPartner.impression_url) +
              '" width="1" height="1" alt="" style="width:1px;height:1px;border:0;position:absolute;opacity:0;pointer-events:none;">'
            : "")
        : "";

      ctaBlock +=
        '<div class="cta-card" style="position:relative;">' +
        '<div class="cta-top-row">' +
        '<span class="cta-pr-tag">' +
        escapeHtml(disclosureLabel) +
        "</span>" +
        '<span class="cta-trust-badge">' +
        escapeHtml(primaryPartner.badge) +
        "</span>" +
        "</div>" +
        '<h3 class="cta-headline">' +
        escapeHtml(primaryPartner.headline) +
        "</h3>" +
        '<p class="cta-service-name">' +
        escapeHtml(primaryPartner.service_name) +
        "</p>" +
        '<ul class="cta-features">' +
        primaryPartner.features
          .map(function (f) {
            return "<li>" + escapeHtml(f) + "</li>";
          })
          .join("") +
        "</ul>" +
        '<a class="cta-btn" href="' +
        escapeHtml(primaryPartner.target_url) +
        '" target="_blank" rel="nofollow sponsored noopener">' +
        "<span>" +
        escapeHtml(primaryPartner.cta_button_text) +
        "</span>" +
        ICONS.external +
        "</a>" +
        primaryPixel +
        kaitoriSecondaryHtml +
        shiroariSecondaryHtml +
        "</div>";
    }
    document.getElementById("akiya-cta-container").innerHTML = ctaBlock;

    const tbody = document.querySelector("#yearly-comparison-table tbody");
    tbody.innerHTML = seriesA
      .map(function (valA, idx) {
        const valB = seriesB[idx];
        const valC = seriesC[idx];
        const diffCB = valC - valB;
        return (
          "<tr>" +
          "<td><strong>" +
          (idx + 1) +
          "年目</strong>" +
          (idx === 2 && kanriRisk === "warn_y3"
            ? '<span class="inline-warn-tag">勧告・特例解除</span>'
            : "") +
          "</td>" +
          '<td class="num num-amber">' +
          formatManYen(valA, true) +
          "</td>" +
          '<td class="num num-vermilion">' +
          formatManYen(valB, true) +
          "</td>" +
          '<td class="num num-green">' +
          formatManYen(valC, true) +
          "</td>" +
          '<td class="num num-strong">+' +
          formatManYen(diffCB, false) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function syncMunicipalitySubsidy(code) {
    selectedMuniCode = code;
    const muni = allMunicipalities.find(function (m) {
      return m.municipality_code === code;
    });
    if (!muni) {
      return;
    }
    const maxMan = Math.round(muni.akiya_demolition_subsidy_max_yen / 10000);
    document.getElementById("subsidy-override-man").value = String(maxMan);
    document.getElementById("akiya-muni-note").textContent =
      muni.prefecture + " " + muni.city_name + "：" + muni.akiya_subsidy_notes;
    document.getElementById("akiya-header-meta").textContent =
      muni.prefecture + " " + muni.city_name + " 除却補助データ反映済";
  }

  function populateMunicipalityDropdown() {
    const sel = document.getElementById("akiya-muni-select");
    sel.innerHTML = allMunicipalities
      .map(function (m) {
        const subLabel =
          m.akiya_demolition_subsidy_max_yen > 0
            ? "上限" + Math.round(m.akiya_demolition_subsidy_max_yen / 10000) + "万円"
            : "個別確認";
        return (
          '<option value="' +
          escapeHtml(m.municipality_code) +
          '"' +
          (m.municipality_code === selectedMuniCode ? " selected" : "") +
          ">" +
          escapeHtml(m.prefecture + " " + m.city_name + "（除却補助：" + subLabel + "）") +
          "</option>"
        );
      })
      .join("");
  }

  function bindEvents() {
    document.getElementById("akiya-muni-select").addEventListener("change", function (e) {
      syncMunicipalitySubsidy(e.target.value);
      recalculate();
    });

    const liveIds = [
      "land-eval-man",
      "land-area-sqm",
      "bldg-eval-man",
      "bldg-tsubo",
      "bldg-struct",
      "upkeep-man",
      "subsidy-override-man",
      "kanri-risk-select",
      "city-plan-tax",
      "buyout-ratio"
    ];
    liveIds.forEach(function (id) {
      document.getElementById(id).addEventListener("input", recalculate);
      document.getElementById(id).addEventListener("change", recalculate);
    });

    Array.from(document.querySelectorAll(".preset-btn")).forEach(function (btn) {
      btn.addEventListener("click", function () {
        const p = PRESETS[btn.getAttribute("data-preset")];
        if (!p) {
          return;
        }
        document.getElementById("land-eval-man").value = String(p.landEvalMan);
        document.getElementById("land-area-sqm").value = String(p.landAreaSqm);
        document.getElementById("bldg-eval-man").value = String(p.bldgEvalMan);
        document.getElementById("bldg-tsubo").value = String(p.bldgTsubo);
        document.getElementById("bldg-struct").value = p.struct;
        document.getElementById("upkeep-man").value = String(p.upkeepMan);
        document.getElementById("buyout-ratio").value = String(p.buyoutRatio);
        recalculate();
      });
    });
  }

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const urlCode = params.get("code");
    if (urlCode) {
      selectedMuniCode = urlCode;
    }

    try {
      const [muniRes, affRes] = await Promise.all([
        fetch("./data/municipalities.json"),
        fetch("./data/affiliate_config.json")
      ]);
      const muniData = await muniRes.json();
      const affData = await affRes.json();

      allMunicipalities = muniData.municipalities || [];
      affiliatePrograms = affData.programs || {};
      disclosureLabel = affData.disclosure_label || disclosureLabel;

      if (!allMunicipalities.some(function (m) { return m.municipality_code === selectedMuniCode; }) && allMunicipalities.length > 0) {
        selectedMuniCode = allMunicipalities[0].municipality_code;
      }

      populateMunicipalityDropdown();
      syncMunicipalitySubsidy(selectedMuniCode);
      bindEvents();
      recalculate();
    } catch (err) {
      document.getElementById("tax-jump-banner").innerHTML =
        '<div class="callout-title">データ読込エラー</div><div>ローカルWebサーバー経由で開いてください: ' +
        escapeHtml(err.message) +
        "</div>";
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
