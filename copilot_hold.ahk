#Requires AutoHotkey v2.0
#SingleInstance Force

; Keep your existing PowerToys Copilot mapping.
; Short press: PowerToys behaves exactly as today -> show/open Autumn PWA.
; Long press: this helper waits for the same Copilot key to be held, then sends
; Autumn's in-PWA private shortcut Ctrl+Alt+Shift+A after the key is released.
;
; Current Microsoft docs say Copilot commonly emits either:
;   Left Shift + Win + F23   (default below)
;   Win + C                  (older/some systems)
;
; If PowerToys "Select" shows Win+C, change the two values below to:
; COPILOT_HOTKEY := "#c"
; COPILOT_ACTION_KEY := "c"

COPILOT_HOTKEY := "#+F23"
COPILOT_ACTION_KEY := "F23"
HOLD_SECONDS := 0.50
AUTUMN_WINDOW_TITLE := "Autumn Companion"

SetTitleMatchMode 2
; Keep the physical Copilot key transparent. PowerToys owns the original mapping.
; Replaying this Windows-reserved combination synthetically can launch native Copilot.
Hotkey "~" COPILOT_HOTKEY, HandleCopilot

HandleCopilot(*) {
    global COPILOT_ACTION_KEY, HOLD_SECONDS, AUTUMN_WINDOW_TITLE

; Released before threshold = short press. Do nothing extra; PowerToys owns it.
    if KeyWait(COPILOT_ACTION_KEY, "T" HOLD_SECONDS)
        return

    ; Long press: wait for physical release so Win/Shift modifiers are no longer held.
    KeyWait COPILOT_ACTION_KEY

    ; PowerToys already opened/raised Autumn on the initial key-down.
    ; Give the PWA a short moment to become foreground, then start Continuous Voice.
    WinWaitActive AUTUMN_WINDOW_TITLE, , 2
    Sleep 120
    Send "^!+a"
}
