window.collectFormData = function () {
  const data = {};

  // ===============================
  // 1️⃣ مفاتيح حرجة (explicit)
  // ===============================
  data["Client Code"]  = document.getElementById("client_code")?.value || "";
  data["Quotation#"]   = document.getElementById("Quotation#")?.value || "";
  data["Model"]        = document.getElementById("model_code")?.value || "";

  const pricingMode = document.getElementById("Pricing_Mode");
  data["Pricing Mode"] = pricingMode ? pricingMode.value : "";

  // ===============================
  // 2️⃣ باقي الفورم (generic)
  // ===============================
  document.querySelectorAll("input, select, textarea").forEach(el => {
    if (!el.id) return;

    if (
      el.id === "client_code" ||
      el.id === "Quotation#" ||
      el.id === "model_code" ||
      el.id === "Pricing_Mode"
    ) {
      return;
    }

    if (el.type === "checkbox") {
      data[el.id] = el.checked;
    } else {
      data[el.id] = el.value;
    }
  });

  // ===============================
  // 3️⃣ 🔥 FIX: Map prices from STATE
  // ===============================
  data["In Stock"] = window.STATE?.localInStockEGP || 0;
  data["New Order"] = window.STATE?.localNewOrderEGP || 0;
  data["overseas_price"] = window.STATE?.overseasUSD || 0;

  return data;
};