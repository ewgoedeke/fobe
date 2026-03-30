export function PdfIndicator({ hasPdf }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${hasPdf ? 'bg-green-500' : 'bg-muted-foreground/30'}`}
      title={hasPdf ? 'PDF available' : 'No PDF'}
    />
  )
}
