import React, { useState, useEffect, FC } from "react";
import {
  definePlugin,
  ToggleField,
  ServerAPI,
  PanelSection,
  PanelSectionRow,
  DropdownItem,
  SliderField,
  Button
} from "decky-frontend-lib";

declare const SteamClient: any;

const translations: Record<string, Record<string, string>> = {
  en: {
    powerSection: "POWER",
    batteryLimit: "Charge Limit (80%)",
    batteryDesc: "Preserves battery lifespan when gaming plugged in",
    rgbSection: "RGB LIGHTING",
    rgbToggle: "Enable Lighting",
    rgbEffect: "Effect",
    rgbSelect: "Select effect",
    fxStatic: "Static",
    fxBreathe: "Breathe",
    fxChroma: "Chroma",
    fxRainbow: "Rainbow",
    vibeSection: "VIBRATION",
    intensity: "Intensity",
    mode: "Mode",
    modeSelect: "Select mode",
    tpSection: "TOUCHPAD",
    tpToggle: "Touchpad Vibration",
    tpDesc: "Enable vibration on touchpad",
    tpIntensity: "Touchpad Intensity",
    testBtn: "Test Vibration 📳",
    lvlOff: "Off",
    lvlLow: "Low",
    lvlMed: "Medium",
    lvlHigh: "High",
    modeFps: "FPS",
    modeRacing: "Racing",
    modeStandard: "Standard",
    modeSpg: "SPG",
    modeRpg: "RPG",
  },
  uk: {
    powerSection: "ЖИВЛЕННЯ",
    batteryLimit: "Обмеження заряду (80%)",
    batteryDesc: "Зберігає ресурс акумулятора під час гри від мережі",
    rgbSection: "ПІДСВІТКА (RGB)",
    rgbToggle: "Увімкнути підсвічування",
    rgbEffect: "Ефект",
    rgbSelect: "Виберіть ефект",
    fxStatic: "Статичний",
    fxBreathe: "Подих",
    fxChroma: "Палітра",
    fxRainbow: "Веселка",
    vibeSection: "ВІБРАЦІЯ",
    intensity: "Інтенсивність",
    mode: "Режим",
    modeSelect: "Виберіть режим",
    tpSection: "ТАЧПАД",
    tpToggle: "Вібрація тачпада",
    tpDesc: "Увімкнути вібрацію на тачпаді",
    tpIntensity: "Інтенсивність тачпада",
    testBtn: "Тест вібрації 📳",
    lvlOff: "Вимк.",
    lvlLow: "Низька",
    lvlMed: "Середня",
    lvlHigh: "Висока",
    modeFps: "FPS",
    modeRacing: "Гонки",
    modeStandard: "Стандарт",
    modeSpg: "SPG",
    modeRpg: "RPG",
  },
  ru: {
    powerSection: "ПИТАНИЕ",
    batteryLimit: "Лимит заряда (80%)",
    batteryDesc: "Сохраняет ресурс аккумулятора при игре от сети",
    rgbSection: "ПОДСВЕТКА (RGB)",
    rgbToggle: "Включить подсветку",
    rgbEffect: "Эффект",
    rgbSelect: "Выберите эффект",
    fxStatic: "Статический",
    fxBreathe: "Дыхание",
    fxChroma: "Палитра",
    fxRainbow: "Радуга",
    vibeSection: "ВИБРАЦИЯ",
    intensity: "Интенсивность",
    mode: "Режим",
    modeSelect: "Выберите режим",
    tpSection: "ТАЧПАД",
    tpToggle: "Вибрация тачпада",
    tpDesc: "Включить вибрацию на тачпаде",
    tpIntensity: "Интенсивность тачпада",
    testBtn: "Тест вибрации 📳",
    lvlOff: "Выкл.",
    lvlLow: "Низкая",
    lvlMed: "Средняя",
    lvlHigh: "Высокая",
    modeFps: "FPS",
    modeRacing: "Гонки",
    modeStandard: "Стандарт",
    modeSpg: "SPG",
    modeRpg: "RPG",
  }
};

const Content: FC<{ serverAPI: ServerAPI }> = ({ serverAPI }) => {
  const [lang, setLang] = useState<string>("en");
  const [batteryLimit, setBatteryLimit] = useState<boolean>(false);
  const [rgbEnabled, setRgbEnabled] = useState<boolean>(false);
  const [rgbEffect, setRgbEffect] = useState<string>("monocolor");

  const [vibeSettings, setVibeSettings] = useState({
    level: 2,
    mode: 2,
    touchpadIntensity: 1,
    touchpadEnabled: true
  });

  useEffect(() => {
    try {
      if (typeof SteamClient !== "undefined" && SteamClient.Localization && SteamClient.Localization.GetLanguage) {
        const steamLang = SteamClient.Localization.GetLanguage();
        if (steamLang === "ukrainian") setLang("uk");
        else if (steamLang === "russian") setLang("ru");
        else setLang("en");
      } else {
        const navLang = navigator.language || "en";
        if (navLang.startsWith("uk")) setLang("uk");
        else if (navLang.startsWith("ru")) setLang("ru");
        else setLang("en");
      }
    } catch (e) {
      setLang("en");
    }

    serverAPI.callPluginMethod<[], boolean>("get_charge_status", {}).then((res) => {
      if (res && res.success) setBatteryLimit(res.result);
    });

      serverAPI.callPluginMethod<[], any>("get_rgb_state", {}).then((res) => {
        if (res && res.success && res.result) {
          setRgbEnabled(res.result.enabled);
          setRgbEffect(res.result.effect);
        }
      });

      serverAPI.callPluginMethod<[], any>("get_settings", {}).then((res) => {
        const data = res?.result || res;
        if (data && data.settings) {
          setVibeSettings({
            level: Number(data.settings.level ?? 2),
                          mode: Number(data.settings.mode ?? 2),
                          touchpadIntensity: Number(data.settings.touchpadIntensity ?? 1),
                          touchpadEnabled: Boolean(data.settings.touchpadEnabled ?? true)
          });
        }
      });
  }, [serverAPI]);

  const t = translations[lang] || translations.en;

  const intensityLabels = [t.lvlOff, t.lvlLow, t.lvlMed, t.lvlHigh];

  const modeOptions = [
    { data: 0, label: t.modeFps },
    { data: 1, label: t.modeRacing },
    { data: 2, label: t.modeStandard },
    { data: 3, label: t.modeSpg },
    { data: 4, label: t.modeRpg },
  ];

  const rgbOptions = [
    { data: "monocolor", label: t.fxStatic },
    { data: "breathe", label: t.fxBreathe },
    { data: "chroma", label: t.fxChroma },
    { data: "rainbow", label: t.fxRainbow },
  ];

  const handleBatteryToggle = async (value: boolean) => {
    setBatteryLimit(value);
    await serverAPI.callPluginMethod("set_charge_status", { enabled: value });
  };

  const handleRgbToggle = async (value: boolean) => {
    setRgbEnabled(value);
    await serverAPI.callPluginMethod("set_rgb_enabled", { enabled: value });
  };

  const handleRgbEffectChange = async (option: { data: string; label: string }) => {
    setRgbEffect(option.data);
    await serverAPI.callPluginMethod("set_rgb_effect", { effect: option.data });
  };

  const handleIntensityChange = async (val: number) => {
    setVibeSettings((prev) => ({ ...prev, level: val }));
    await serverAPI.callPluginMethod("set_intensity", { level: val });
  };

  const handleModeChange = async (option: { data: number; label: string }) => {
    const val = option.data;
    setVibeSettings((prev) => ({ ...prev, mode: val }));
    await serverAPI.callPluginMethod("set_rumble_mode", { mode: val });
  };

  const handleTpIntensityChange = async (val: number) => {
    setVibeSettings((prev) => ({ ...prev, touchpadIntensity: val }));
    await serverAPI.callPluginMethod("set_touchpad_intensity", { level: val });
  };

  const handleTpToggle = async (value: boolean) => {
    setVibeSettings((prev) => ({ ...prev, touchpadEnabled: value }));
    await serverAPI.callPluginMethod("set_touchpad_enabled", { enabled: value });
  };

  const handleTestVibe = async () => {
    await serverAPI.callPluginMethod("test_vibration", { duration_ms: 500 });
  };

  return (
    <>
    <PanelSection title={t.powerSection}>
    <PanelSectionRow>
    <ToggleField
    label={t.batteryLimit}
    description={t.batteryDesc}
    checked={batteryLimit}
    onChange={handleBatteryToggle}
    />
    </PanelSectionRow>
    </PanelSection>

    <PanelSection title={t.rgbSection}>
    <PanelSectionRow>
    <ToggleField
    label={t.rgbToggle}
    checked={rgbEnabled}
    onChange={handleRgbToggle}
    />
    </PanelSectionRow>

    {rgbEnabled && (
      <PanelSectionRow>
      <DropdownItem
      label={t.rgbEffect}
      menuLabel={t.rgbSelect}
      selectedOption={rgbEffect}
      rgOptions={rgbOptions}
      onChange={handleRgbEffectChange}
      />
      </PanelSectionRow>
    )}
    </PanelSection>

    <PanelSection title={t.vibeSection}>
    <PanelSectionRow>
    <SliderField
    label={t.intensity}
    description={intensityLabels[vibeSettings.level] || t.lvlMed}
    min={0}
    max={3}
    step={1}
    value={vibeSettings.level}
    onChange={handleIntensityChange}
    />
    </PanelSectionRow>

    <PanelSectionRow>
    <DropdownItem
    label={t.mode}
    menuLabel={t.modeSelect}
    selectedOption={vibeSettings.mode}
    rgOptions={modeOptions}
    onChange={handleModeChange}
    />
    </PanelSectionRow>
    </PanelSection>

    <PanelSection title={t.tpSection}>
    <PanelSectionRow>
    <ToggleField
    label={t.tpToggle}
    description={t.tpDesc}
    checked={vibeSettings.touchpadEnabled}
    onChange={handleTpToggle}
    />
    </PanelSectionRow>

    {vibeSettings.touchpadEnabled && (
      <PanelSectionRow>
      <SliderField
      label={t.tpIntensity}
      description={intensityLabels[vibeSettings.touchpadIntensity] || t.lvlLow}
      min={0}
      max={3}
      step={1}
      value={vibeSettings.touchpadIntensity}
      onChange={handleTpIntensityChange}
      />
      </PanelSectionRow>
    )}

    <PanelSectionRow>
    <Button onClick={handleTestVibe} skinless style={{ width: "100%", textAlign: "center" }}>
    {t.testBtn}
    </Button>
    </PanelSectionRow>
    </PanelSection>
    </>
  );
};

export default definePlugin((serverApi: ServerAPI) => {
  return {
    title: <div>Legion Control</div>,
    icon: <span>⚡</span>,
    content: <Content serverAPI={serverApi} />,
  };
});
