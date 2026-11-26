(function () {
  "use strict";

  const ICONS = {
    alert:
      '<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M12 3L2 21h20L12 3z"></path><line x1="12" y1="9" x2="12" y2="14"></line><circle cx="12" cy="17.5" r="0.9" fill="currentColor"></circle></svg>',
    check:
      '<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M8.5 12.5l2.5 2.5 4.5-5"></path></svg>',
    info:
      '<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><line x1="12" y1="11" x2="12" y2="16"></line><circle cx="12" cy="8" r="0.9" fill="currentColor"></circle></svg>',
    external:
      '<svg class="icon-inline" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>'
  };

  const MARKET_COSTS = {
    suzumebachi: {
      label: "スズメバチ駆除",
      affiliateKey: "hachi_110",
      locations: {
        eaves: { label: "軒下・ベランダ等の低所", min: 13000, max: 25000, baseFee: 13000, addFee: "0〜12,000円（巣径・時期加算）" },
        attic_high: { label: "屋根裏・壁内・2階以上の高所", min: 18000, max: 45000, baseFee: 15000, addFee: "5,000〜30,000円（高所梯子・閉鎖空間作業）" },
        underfloor: { label: "床下・土中・狭小箇所", min: 25000, max: 55000, baseFee: 16000, addFee: "9,000〜39,000円（掘削・床下進入作業）" }
      }
    },
    ashinagabachi: {
      label: "アシナガバチ・ミツバチ駆除",
      affiliateKey: "hachi_110",
      locations: {
        eaves: { label: "軒下・ベランダ等の低所", min: 8800, max: 16000, baseFee: 8800, addFee: "0〜7,200円（サイズ・再発防止処置）" },
        attic_high: { label: "屋根裏・壁内・2階以上の高所", min: 13000, max: 26000, baseFee: 9800, addFee: "3,200〜16,200円（高所・屋根裏加算）" },
        underfloor: { label: "床下・植栽奥・換気口内", min: 16000, max: 32000, baseFee: 11000, addFee: "5,000〜21,000円（開口・難所作業加算）" }
      }
    },
    shiroari: {
      label: "シロアリ駆除（5年保証目安）",
      affiliateKey: "shiroari_110",
      locations: {
        eaves: { label: "部分処置・小規模床下（約30㎡目安）", min: 65000, max: 110000, baseFee: 65000, addFee: "平米単価 約1,800〜2,500円/㎡" },
        attic_high: { label: "一般戸建1階床下全面（約50〜65㎡目安）", min: 90000, max: 165000, baseFee: 90000, addFee: "玄関土間穿孔・浴室周り重点処理含む" },
        underfloor: { label: "広範囲被害・腐朽補修を伴う床下", min: 120000, max: 240000, baseFee: 120000, addFee: "ベイト工法・木部補強オプション時変動" }
      }
    },
    gaiju: {
      label: "ハクビシン・アライグマ・ネズミ駆除",
      affiliateKey: "gaiju_110",
      locations: {
        eaves: { label: "初期侵入・部分的侵入口封鎖", min: 35000, max: 75000, baseFee: 35000, addFee: "追い出し＋金網・パンチング封鎖" },
        attic_high: { label: "屋根裏営巣・フン清掃殺菌＋外周封鎖", min: 80000, max: 190000, baseFee: 60000, addFee: "20,000〜130,000円（清掃消毒・高所封鎖箇所数）" },
        underfloor: { label: "床下・壁内広範囲侵入＋汚損対応", min: 120000, max: 280000, baseFee: 80000, addFee: "40,000〜200,000円（広範囲封鎖・消臭殺菌一式）" }
      }
    }
  };

  let allMunicipalities = [];
  let affiliatePrograms = {};
  let disclosureLabel = "PR・広告提携枠";
  let selectedCode = "08201";
  let activePattern = "ALL";

  function katakanaToHiragana(str) {
    return str.replace(/[\u30a1-\u30f6]/g, function (ch) {
      return String.fromCharCode(ch.charCodeAt(0) - 0x60);
    });
  }

  function formatYen(num) {
    return num.toLocaleString("ja-JP") + "円";
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function computeSubsidyEstimate(muni, pestType, minCost, maxCost) {
    const sub = muni.suzumebachi_subsidy;
    if (pestType === "shiroari" || pestType === "gaiju") {
      return { minSub: 0, maxSub: 0, directDispatch: false, eligible: false };
    }
    if (pestType === "ashinagabachi" && !sub.ashinagabachi_covered) {
      return { minSub: 0, maxSub: 0, directDispatch: false, eligible: false };
    }
    if (!sub.available) {
      return { minSub: 0, maxSub: 0, directDispatch: false, eligible: false };
    }
    if (sub.max_yen === 0 && sub.city_designated_only) {
      return { minSub: minCost, maxSub: maxCost, directDispatch: true, eligible: true };
    }
    const minHalf = Math.min(Math.floor(minCost * 0.5), sub.max_yen);
    const maxHalf = Math.min(Math.floor(maxCost * 0.5), sub.max_yen);
    return { minSub: minHalf, maxSub: maxHalf, directDispatch: false, eligible: true };
  }

  function populatePrefectureOptions() {
    const prefSelect = document.getElementById("pref-select");
    const seen = new Set();
    allMunicipalities.forEach(function (m) {
      if (!seen.has(m.prefecture)) {
        seen.add(m.prefecture);
        const opt = document.createElement("option");
        opt.value = m.prefecture;
        opt.textContent = m.prefecture;
        prefSelect.appendChild(opt);
      }
    });
  }

  function renderStats(dataset) {
    const total = allMunicipalities.length;
    const subsidyCount = allMunicipalities.filter(function (m) {
      return m.suzumebachi_subsidy.available;
    }).length;
    const suitCount = allMunicipalities.filter(function (m) {
      return m.suzumebachi_subsidy.protective_suit_loan;
    }).length;
    const akiyaCount = allMunicipalities.filter(function (m) {
      return m.akiya_demolition_subsidy_max_yen > 0;
    }).length;

    document.getElementById("stat-total-cities").textContent = total + "市区町村";
    document.getElementById("stat-subsidy-cities").textContent = subsidyCount + "件";
    document.getElementById("stat-suit-cities").textContent = suitCount + "件";
    document.getElementById("stat-akiya-cities").textContent = akiyaCount + "件";
    document.getElementById("dataset-meta-banner").textContent = "最終確認日: " + dataset.generated_at;
  }

  function getFilteredMunicipalities() {
    const pref = document.getElementById("pref-select").value;
    const rawQuery = document.getElementById("city-search-input").value.trim();
    const normQuery = katakanaToHiragana(rawQuery.toLowerCase());

    return allMunicipalities.filter(function (m) {
      if (pref !== "ALL" && m.prefecture !== pref) {
        return false;
      }
      if (activePattern !== "ALL" && m.rule_pattern !== activePattern) {
        return false;
      }
      if (normQuery) {
        const hayKanji = (m.prefecture + m.city_name).toLowerCase();
        const hayKana = m.reading_kana;
        if (!hayKanji.includes(normQuery) && !hayKana.includes(normQuery)) {
          return false;
        }
      }
      return true;
    });
  }

  function renderMunicipalityList() {
    const filtered = getFilteredMunicipalities();
    const listEl = document.getElementById("muni-list");
    document.getElementById("filtered-count-label").textContent = filtered.length + "件";

    if (filtered.length === 0) {
      listEl.innerHTML =
        '<div class="callout-box callout-info" style="margin-top:12px;">' +
        '<div class="callout-title">' +
        ICONS.info +
        "<span>該当する市区町村が見つかりません</span></div>" +
        "<div>都道府県を「全国すべて」に戻すか、ひらがな（例：よこはま、せたがや）でお試しください。</div>" +
        "</div>";
      return;
    }

    if (!filtered.some(function (m) { return m.municipality_code === selectedCode; })) {
      selectedCode = filtered[0].municipality_code;
    }

    listEl.innerHTML = filtered
      .map(function (m) {
        const isSelected = m.municipality_code === selectedCode;
        return (
          '<button type="button" role="option" aria-selected="' +
          (isSelected ? "true" : "false") +
          '" class="muni-item' +
          (isSelected ? " selected" : "") +
          '" data-code="' +
          escapeHtml(m.municipality_code) +
          '">' +
          '<div class="muni-item-top">' +
          '<div><span class="muni-name">' +
          escapeHtml(m.prefecture + " " + m.city_name) +
          '</span><span class="muni-kana">' +
          escapeHtml(m.reading_kana) +
          "</span></div>" +
          '<span class="rule-badge badge-' +
          escapeHtml(m.rule_pattern) +
          '">' +
          escapeHtml(m.rule_badge_label) +
          "</span>" +
          "</div>" +
          '<div class="muni-dept">' +
          escapeHtml(m.official_dept_name) +
          " ・ 空き家解体補助: " +
          (m.akiya_demolition_subsidy_max_yen > 0
            ? "上限" + formatYen(m.akiya_demolition_subsidy_max_yen)
            : "個別確認") +
          "</div>" +
          "</button>"
        );
      })
      .join("");

    Array.from(listEl.querySelectorAll(".muni-item")).forEach(function (btn) {
      btn.addEventListener("click", function () {
        selectedCode = btn.getAttribute("data-code");
        renderMunicipalityList();
        renderDetailPanel();
      });
    });
  }

  function renderDetailPanel() {
    const muni = allMunicipalities.find(function (m) {
      return m.municipality_code === selectedCode;
    });
    if (!muni) {
      return;
    }

    const headerAkiyaLink = document.getElementById("header-akiya-link");
    if (headerAkiyaLink) {
      headerAkiyaLink.href = "./akiya.html?code=" + encodeURIComponent(muni.municipality_code);
    }

    const pestType = document.getElementById("pest-type-select").value;
    const locKey = document.getElementById("nest-loc-select").value;
    const pestInfo = MARKET_COSTS[pestType];
    const locInfo = pestInfo.locations[locKey];
    const sub = muni.suzumebachi_subsidy;
    const est = computeSubsidyEstimate(muni, pestType, locInfo.min, locInfo.max);

    const netMin = Math.max(0, locInfo.min - est.maxSub);
    const netMax = Math.max(0, locInfo.max - est.minSub);

    let alertsHtml = "";

    if (pestType === "suzumebachi" || pestType === "ashinagabachi") {
      if (pestType === "ashinagabachi" && sub.available && !sub.ashinagabachi_covered) {
        alertsHtml +=
          '<div class="callout-box callout-warning">' +
          '<div class="callout-title">' +
          ICONS.alert +
          "<span>アシナガバチは自治体補助の対象外です</span></div>" +
          "<div>" +
          escapeHtml(muni.city_name) +
          "の補助・委託制度は<strong>スズメバチ限定</strong>のため、アシナガバチは自己負担となります。" +
          (sub.protective_suit_loan ? "なお、<strong>防護服の無料貸出</strong>は相談可能です。" : "") +
          "</div></div>";
      } else if (sub.city_designated_only) {
        alertsHtml +=
          '<div class="callout-box callout-danger">' +
          '<div class="callout-title">' +
          ICONS.alert +
          "<span>業者へ依頼する前に「" +
          escapeHtml(muni.official_dept_name) +
          "」へ連絡してください</span></div>" +
          "<div><strong>" +
          escapeHtml(muni.city_name) +
          "は自治体委託または指定登録業者限定です。</strong>一般の民間業者を直接呼ぶと補助・無償駆除の対象外になります。平日の開庁時間内は先に窓口へ相談してください。</div>" +
          "</div>";
      } else if (sub.available && sub.pre_application_required) {
        alertsHtml +=
          '<div class="callout-box callout-danger">' +
          '<div class="callout-title">' +
          ICONS.alert +
          "<span>事前申請が必須です（事後申請は対象外）</span></div>" +
          "<div><strong>" +
          escapeHtml(muni.city_name) +
          "の補助金（上限" +
          formatYen(sub.max_yen) +
          "）は作業前の申請が必要です。</strong>見積もり時に「事前申請用の見積書と駆除前の巣の写真が必要」と伝えてください。</div>" +
          "</div>";
      } else if (sub.available) {
        alertsHtml +=
          '<div class="callout-box callout-success">' +
          '<div class="callout-title">' +
          ICONS.check +
          "<span>補助金制度あり：" +
          escapeHtml(sub.rate_text) +
          "</span></div>" +
          "<div><strong>駆除前後の写真・内訳明記の領収書原本</strong>を揃えて申請することで補助金を受け取れます（予算上限に達し次第終了）。</div>" +
          "</div>";
      } else if (sub.protective_suit_loan) {
        alertsHtml +=
          '<div class="callout-box callout-info">' +
          '<div class="callout-title">' +
          ICONS.info +
          "<span>補助金なし・防護服の無料貸出あり</span></div>" +
          "<div>現金給付の補助はありませんが防護服の貸出があります。ただし<strong>スズメバチや高所・屋根裏の自力駆除は重篤な刺傷・転落リスクが高い</strong>ため、専門業者への依頼を推奨します。</div>" +
          "</div>";
      } else {
        alertsHtml +=
          '<div class="callout-box callout-info">' +
          '<div class="callout-title">' +
          ICONS.info +
          "<span>" +
          escapeHtml(muni.city_name) +
          "は補助金・防護服貸出ともになし</span></div>" +
          "<div>公的な費用助成はないため、作業前に確定総額を提示する専門業者へ直接見積もりを依頼してください。</div>" +
          "</div>";
      }

      if (sub.required_evidence && sub.required_evidence.length > 0 && (pestType === "suzumebachi" || sub.ashinagabachi_covered)) {
        alertsHtml +=
          '<div class="callout-box callout-warning">' +
          '<div class="callout-title">' +
          ICONS.info +
          "<span>申請時に必要な確認項目</span></div>" +
          '<ul class="callout-list">' +
          sub.required_evidence
            .map(function (ev) {
              return "<li>" + escapeHtml(ev) + "</li>";
            })
            .join("") +
          "</ul></div>";
      }
    } else {
      alertsHtml +=
        '<div class="callout-box callout-info">' +
        '<div class="callout-title">' +
        ICONS.info +
        "<span>" +
        escapeHtml(muni.city_name) +
        "のシロアリ・害獣ルール</span></div>" +
        "<div>" +
        escapeHtml(muni.termites_wildlife_notes) +
        "</div></div>";
    }

    const officialQueryUrl =
      "https://www.google.com/search?q=" + encodeURIComponent(muni.official_search_query);

    const subsidyDisplay = est.directDispatch
      ? "自治体委託（原則0円）"
      : est.eligible
      ? "▲" + formatYen(est.minSub) + "〜" + formatYen(est.maxSub)
      : "0円（対象外）";

    const netDisplay = est.directDispatch
      ? "0円（要件適合時）"
      : formatYen(netMin) + "〜" + formatYen(netMax);

    const partner = affiliatePrograms[pestInfo.affiliateKey];
    const comparePartner = affiliatePrograms.pest_rcleaning;
    let ctaHtml = "";
    if (partner) {
      const designatedCaution =
        sub.city_designated_only && (pestType === "suzumebachi" || sub.ashinagabachi_covered)
          ? '<p class="cta-designated-note">平日の日中はまず「' +
            escapeHtml(muni.official_dept_name) +
            "」へ指定・委託の対象かご確認ください。夜間・休日の緊急時や対象外箇所では下記見積もりが利用できます。</p>"
          : "";

      const primaryPixel = partner.impression_url
        ? '<img src="' +
          escapeHtml(partner.impression_url) +
          '" width="1" height="1" alt="" style="width:1px;height:1px;border:0;position:absolute;opacity:0;pointer-events:none;">'
        : "";

      const secondaryBtnHtml = comparePartner
        ? '<a class="cta-btn-secondary" href="' +
          escapeHtml(comparePartner.target_url) +
          '" target="_blank" rel="nofollow sponsored noopener">' +
          "<span>" +
          escapeHtml(comparePartner.cta_button_text) +
          "</span>" +
          ICONS.external +
          "</a>" +
          (comparePartner.impression_url
            ? '<img src="' +
              escapeHtml(comparePartner.impression_url) +
              '" width="1" height="1" alt="" style="width:1px;height:1px;border:0;position:absolute;opacity:0;pointer-events:none;">'
            : "")
        : "";

      ctaHtml =
        '<div class="cta-card" style="position:relative;">' +
        '<div class="cta-top-row">' +
        '<span class="cta-pr-tag">' +
        escapeHtml(disclosureLabel) +
        "</span>" +
        '<span class="cta-trust-badge">' +
        escapeHtml(partner.badge) +
        "</span>" +
        "</div>" +
        '<h3 class="cta-headline">' +
        escapeHtml(partner.headline) +
        "</h3>" +
        '<p class="cta-service-name">' +
        escapeHtml(partner.service_name) +
        "</p>" +
        designatedCaution +
        '<ul class="cta-features">' +
        partner.features
          .map(function (f) {
            return "<li>" + escapeHtml(f) + "</li>";
          })
          .join("") +
        "</ul>" +
        '<a class="cta-btn" href="' +
        escapeHtml(partner.target_url) +
        '" target="_blank" rel="nofollow sponsored noopener">' +
        "<span>" +
        escapeHtml(partner.cta_button_text) +
        "</span>" +
        ICONS.external +
        "</a>" +
        primaryPixel +
        secondaryBtnHtml +
        "</div>";
    }

    const akiyaMax = muni.akiya_demolition_subsidy_max_yen;
    const akiyaBridgeHtml =
      '<div class="akiya-bridge-card">' +
      "<h4>相続した実家・空き家の被害でお悩みですか？</h4>" +
      "<p>" +
      escapeHtml(muni.city_name) +
      "には" +
      escapeHtml(muni.akiya_subsidy_notes) +
      "がありますが、売却前に更地へ解体すると翌年から<strong>土地の固定資産税が約3.5〜4.2倍に増額</strong>されます。</p>" +
      '<a class="akiya-bridge-link" href="./akiya.html?code=' +
      encodeURIComponent(muni.municipality_code) +
      '">' +
      escapeHtml(muni.city_name) +
      "の空き家10年損益（解体補助 " +
      (akiyaMax > 0 ? "上限" + formatYen(akiyaMax) : "要確認") +
      " vs 現況買取）を試算する →</a>" +
      "</div>";

    const container = document.getElementById("result-detail-container");
    container.innerHTML =
      '<div class="result-header-row">' +
      '<div><span class="result-city-name">' +
      escapeHtml(muni.prefecture + " " + muni.city_name) +
      '</span><span class="rule-badge badge-' +
      escapeHtml(muni.rule_pattern) +
      '">' +
      escapeHtml(muni.rule_badge_label) +
      "</span></div>" +
      '<a class="official-verify-link" href="' +
      escapeHtml(officialQueryUrl) +
      '" target="_blank" rel="noopener noreferrer">' +
      "<span>公式要綱を検索</span>" +
      ICONS.external +
      "</a>" +
      "</div>" +
      alertsHtml +
      '<div class="cost-breakdown-box">' +
      '<div class="cost-section-label">' +
      escapeHtml(pestInfo.label) +
      "（" +
      escapeHtml(locInfo.label) +
      "）の費用目安</div>" +
      '<div class="cost-grid">' +
      '<div class="cost-cell">' +
      '<div class="cost-cell-label">適正市場相場（税込）</div>' +
      '<div class="cost-cell-val">' +
      formatYen(locInfo.min) +
      "〜" +
      formatYen(locInfo.max) +
      "</div>" +
      "</div>" +
      '<div class="cost-cell subsidy-green">' +
      '<div class="cost-cell-label">自治体補助見込</div>' +
      '<div class="cost-cell-val">' +
      subsidyDisplay +
      "</div>" +
      "</div>" +
      '<div class="cost-cell highlight">' +
      '<div class="cost-cell-label">実質自己負担の目安</div>' +
      '<div class="cost-cell-val">' +
      netDisplay +
      "</div>" +
      "</div>" +
      "</div>" +
      '<table class="data-table">' +
      "<tbody>" +
      "<tr><th>基本作業料目安</th><td>" +
      formatYen(locInfo.baseFee) +
      " 前後（薬剤・標準防護・撤去含む）</td></tr>" +
      "<tr><th>場所・難易度加算</th><td>" +
      escapeHtml(locInfo.addFee) +
      "</td></tr>" +
      "<tr><th>担当窓口</th><td>" +
      escapeHtml(muni.official_dept_name) +
      " ／ " +
      escapeHtml(sub.rate_text) +
      "</td></tr>" +
      "<tr><th>貸出制度</th><td>防護服: " +
      (sub.protective_suit_loan ? "あり（要予約）" : "なし") +
      " ・ 害獣わな相談: " +
      (muni.wildlife_trap_loan ? "あり" : "なし") +
      "</td></tr>" +
      "</tbody></table>" +
      "</div>" +
      ctaHtml +
      akiyaBridgeHtml;
  }

  function bindEvents() {
    document.getElementById("pref-select").addEventListener("change", function () {
      renderMunicipalityList();
      renderDetailPanel();
    });
    document.getElementById("city-search-input").addEventListener("input", function () {
      renderMunicipalityList();
      renderDetailPanel();
    });
    document.getElementById("pest-type-select").addEventListener("change", renderDetailPanel);
    document.getElementById("nest-loc-select").addEventListener("change", renderDetailPanel);

    Array.from(document.querySelectorAll(".filter-chip")).forEach(function (chip) {
      chip.addEventListener("click", function () {
        Array.from(document.querySelectorAll(".filter-chip")).forEach(function (c) {
          c.classList.remove("active");
        });
        chip.classList.add("active");
        activePattern = chip.getAttribute("data-pattern");
        renderMunicipalityList();
        renderDetailPanel();
      });
    });
  }

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const urlCode = params.get("code");
    if (urlCode) {
      selectedCode = urlCode;
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

      populatePrefectureOptions();
      renderStats(muniData);
      bindEvents();
      renderMunicipalityList();
      renderDetailPanel();
    } catch (err) {
      document.getElementById("result-detail-container").innerHTML =
        '<div class="callout-box callout-danger"><div class="callout-title">データ読込エラー</div><div>ローカルWebサーバー経由でアクセスしてください: ' +
        escapeHtml(err.message) +
        "</div></div>";
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
