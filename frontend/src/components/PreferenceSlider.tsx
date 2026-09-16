import { formatPercent } from "../utils/format";

interface PreferenceSliderProps {
  id: string;
  label: string;
  hint: string;
  value: number;
  share: number;
  onChange: (value: number) => void;
}

export function PreferenceSlider({
  id,
  label,
  hint,
  value,
  share,
  onChange,
}: PreferenceSliderProps) {
  return (
    <div className="preference">
      <div className="preference__header">
        <label htmlFor={id}>{label}</label>
        <span className="preference__share" title="Share of the overall score">
          {formatPercent(share)}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={0}
        max={100}
        step={5}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        aria-describedby={`${id}-hint`}
      />
      <p id={`${id}-hint`} className="preference__hint">
        {hint}
      </p>
    </div>
  );
}
