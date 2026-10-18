// Abre e fecha o menu no celular. É o único JavaScript do site.
(function () {
  var botao = document.getElementById('menuBotao');
  var menu = document.getElementById('menu');
  if (!botao || !menu) return;

  function alternar(aberto) {
    menu.classList.toggle('aberto', aberto);
    botao.setAttribute('aria-expanded', String(aberto));
  }

  botao.addEventListener('click', function () {
    alternar(!menu.classList.contains('aberto'));
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') alternar(false);
  });
})();
