// "1 tick", "2 ticks": a count with its noun in the right number
export const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
