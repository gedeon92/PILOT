// Applique le mode d'affichage choisi (clair ou sombre) avant le premier affichage,
// pour éviter un éclair de l'autre couleur au chargement. Sombre par défaut.
;(function () {
  var theme = 'dark'
  try {
    if (localStorage.getItem('pilot-theme') === 'light') theme = 'light'
  } catch {
    /* stockage indisponible : on garde le mode sombre */
  }
  document.documentElement.dataset.theme = theme
})()
