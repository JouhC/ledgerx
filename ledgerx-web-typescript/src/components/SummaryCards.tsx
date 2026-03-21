type SummaryCardProps = {
  label: string;
  value: string;
  sub?: string;
};

export function SummaryCard({ label, value, sub }: SummaryCardProps) {
  return (
    <div className="rounded-2xl bg-slate-50 p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      {sub ? <div className="mt-1 text-xs text-slate-500">{sub}</div> : null}
    </div>
  );
}