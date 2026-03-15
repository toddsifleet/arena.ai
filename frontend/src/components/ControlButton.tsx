import type { Component } from "solid-js";

interface ControlButtonProps {
  active: boolean;
  danger: boolean;
  label: string;
  onClick: () => void;
}

const ControlButton: Component<ControlButtonProps> = (props) => (
  <button
    type="button"
    onClick={props.onClick}
    class={`rounded-full h-9 px-4 text-xs font-medium transition-colors ${
      props.danger
        ? "bg-red-500/15 text-red-400 hover:bg-red-500/25"
        : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
    }`}
  >
    {props.label}
  </button>
);

export default ControlButton;
