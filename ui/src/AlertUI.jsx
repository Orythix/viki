import { useEffect } from 'react'

/**
 * Custom alert/confirm UI. Use instead of window.alert / window.confirm.
 * @param {boolean} open - Whether the dialog is visible
 * @param {string} message - Text to show
 * @param {'alert'|'confirm'} variant - alert = one button (OK), confirm = Cancel + Confirm
 * @param {string} [confirmLabel='Confirm'] - Label for confirm button
 * @param {string} [cancelLabel='Cancel'] - Label for cancel button (confirm only)
 * @param {function} onConfirm - Called when user confirms or clicks OK
 * @param {function} onCancel - Called when user cancels (confirm only)
 * @param {function} onClose - Called when backdrop is clicked (optional; can call onCancel)
 */
export default function AlertUI({
  open,
  message,
  variant = 'confirm',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
  onClose,
}) {
  const handleClose = onClose || onCancel

  useEffect(() => {
    if (!open) return
    const handleEscape = (e) => {
      if (e.key === 'Escape') handleClose?.()
    }
    document.addEventListener('keydown', handleEscape)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [open, handleClose])

  if (!open) return null

  return (
    <div
      className="alert-ui-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="alert-ui-message"
      onClick={(e) => e.target === e.currentTarget && handleClose?.()}
    >
      <div className="alert-ui-card">
        <p id="alert-ui-message" className="alert-ui-message">{message}</p>
        <div className="alert-ui-actions">
          {variant === 'confirm' && (
            <button type="button" className="alert-ui-btn alert-ui-btn-cancel" onClick={onCancel}>
              {cancelLabel}
            </button>
          )}
          <button type="button" className="alert-ui-btn alert-ui-btn-confirm" onClick={onConfirm}>
            {variant === 'alert' ? 'OK' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
