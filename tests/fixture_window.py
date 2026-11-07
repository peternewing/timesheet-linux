import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk
app=Gtk.Application(application_id='org.local.CaptureFixture')
def activate(app):
    w=Gtk.ApplicationWindow(application=app,title='Time Sheet capture fixture',default_width=400,default_height=200)
    w.set_child(Gtk.Label(label='Isolated foreground-capture test'));w.present()
app.connect('activate',activate);app.run([])
