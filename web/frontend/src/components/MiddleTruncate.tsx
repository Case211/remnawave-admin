import { cn } from '@/lib/utils'

/**
 * Текст с обрезкой в СЕРЕДИНЕ: хвост виден всегда.
 *
 * Ноды называют с номером в конце («Финляндия_6», «Foreign Netherlands 2»),
 * и обычный `truncate` съедал именно его — в узких карточках оставались
 * неразличимые «Финляндия…» и «Foreign Nethe…».
 *
 * Обрезка живёт на CSS, а не на подсчёте символов: голова сжимается по
 * реальной ширине контейнера, хвост не сжимается никогда. Поэтому имя
 * подстраивается под любую ширину и не зависит от шрифта.
 */
export function MiddleTruncate({
  text,
  tailChars = 3,
  className,
}: {
  text: string
  /** Сколько символов держать нетронутыми справа */
  tailChars?: number
  className?: string
}) {
  // У короткого имени хвост отрезать нечего — оно и так влезает
  const tailLength = Math.min(tailChars, Math.floor(text.length / 2))
  const head = tailLength > 0 ? text.slice(0, text.length - tailLength) : text
  const tail = tailLength > 0 ? text.slice(text.length - tailLength) : ''

  return (
    <span className={cn('flex items-center min-w-0', className)} title={text}>
      <span className="truncate min-w-0">{head}</span>
      {tail && <span className="shrink-0 whitespace-pre">{tail}</span>}
    </span>
  )
}
