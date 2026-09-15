self.addEventListener('push', function(event) {
    let data = { title: "Nuevo Mensaje", body: "Has recibido un mensaje en Rotoblessing." };
    if (event.data) {
        data = event.data.json();
    }
    const options = {
        body: data.body,
        icon: '/static/favicon.ico' // Asegúrate de tener un ícono o ajusta la ruta si es necesario
    };
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});
