"""The app's own widgets (ui.py), driven with real mouse events on a Tk window."""
import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ui
from ui import Button, Card, Field, NavItem, Segmented, Slider, Switch, shape


class UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.geometry("+-2000+0")  # off screen: the tests click through events, not the mouse

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.frame = tk.Frame(self.root, bg=ui.BG)
        self.frame.pack()

    def tearDown(self):
        self.frame.destroy()

    def show(self, widget):
        widget.pack()
        self.root.update()
        return widget

    def click(self, widget, x, y, release_at=None):
        widget.event_generate("<ButtonPress-1>", x=x, y=y)
        widget.event_generate("<ButtonRelease-1>", x=release_at[0] if release_at else x,
                              y=release_at[1] if release_at else y)
        self.root.update()

    # --- shapes ----------------------------------------------------------------------------------

    def test_shapes_are_made_once(self):
        a = shape(self.root, 40, 20, 6, ui.ACCENT)
        self.assertIs(shape(self.root, 40, 20, 6, ui.ACCENT), a)
        self.assertIsNot(shape(self.root, 40, 20, 6, ui.FIELD), a)
        self.assertEqual((a.width(), a.height()), (40, 20))

    def test_shapes_have_see_through_corners(self):
        from PIL import ImageTk  # noqa: F401 - the image's pixels, through Tk
        image = shape(self.root, 30, 30, 10, "#ffffff")
        tk_image = image._PhotoImage__photo
        self.assertEqual(tk_image.transparency_get(0, 0), True)
        self.assertEqual(tk_image.transparency_get(15, 15), False)

    # --- button ----------------------------------------------------------------------------------

    def test_button_runs_its_command_on_release_inside(self):
        clicks = []
        button = self.show(Button(self.frame, "Save", lambda: clicks.append(1), "primary"))
        self.click(button, 5, 5)
        self.assertEqual(clicks, [1])
        self.click(button, 5, 5, release_at=(-20, -20))  # dragged off before letting go: cancelled
        self.assertEqual(clicks, [1])

    def test_button_text_and_width(self):
        button = self.show(Button(self.frame, "(none)", None, width=200))
        width = button.winfo_reqwidth()
        self.assertEqual(width, ui.px(button, 200))
        button.set("Ctrl+Shift+F12", ui.WARN)
        self.assertEqual(button.winfo_reqwidth(), width)  # fixed width: the hotkey list stays aligned
        self.assertEqual(button.itemcget(button.find_all()[-1], "text"), "Ctrl+Shift+F12")
        self.assertEqual(button.itemcget(button.find_all()[-1], "fill"), ui.WARN)

    def test_every_kind_draws(self):
        for kind in ui.KINDS:
            button = self.show(Button(self.frame, kind, None, kind, icon=ui.ICONS["folder"]))
            self.assertTrue(button.find_all())

    # --- choices ---------------------------------------------------------------------------------

    def test_segmented_picks_the_clicked_option(self):
        variable = tk.StringVar(self.root, value="pt")
        changes = []
        control = self.show(Segmented(self.frame, variable, [("pt", "Português"), ("en", "English")],
                                      lambda: changes.append(variable.get())))
        right = control.winfo_width() - 10
        self.click(control, right, 10)
        self.assertEqual((variable.get(), changes), ("en", ["en"]))
        self.click(control, right, 10)  # already chosen: nothing changes
        self.assertEqual(changes, ["en"])
        self.click(control, 10, 10)
        self.assertEqual(variable.get(), "pt")

    def test_segmented_follows_its_variable(self):
        variable = tk.IntVar(self.root, value=1)
        control = self.show(Segmented(self.frame, variable, [(1, "1 smite"), (2, "2 smites")]))
        variable.set(2)
        self.root.update()
        lit = [control.itemcget(i, "text") for i in control.find_all()
               if control.type(i) == "text" and control.itemcget(i, "fill") == "#ffffff"]
        self.assertEqual(lit, ["2 smites"])
        control.destroy()
        variable.set(1)  # no error once the control is gone

    def test_switch(self):
        variable = tk.BooleanVar(self.root, value=True)
        changes = []
        switch = self.show(Switch(self.frame, variable, lambda: changes.append(variable.get())))
        self.click(switch, 5, 5)
        self.assertEqual((variable.get(), changes), (False, [False]))
        self.click(switch, 5, 5)
        self.assertEqual((variable.get(), changes), (True, [False, True]))

    # --- slider ----------------------------------------------------------------------------------

    def test_slider_steps_and_limits(self):
        variable = tk.IntVar(self.root, value=80)
        moved = []
        slider = self.show(Slider(self.frame, variable, 70, 160, 10, length=180, command=moved.append))
        self.assertEqual(slider.value_at(-500), 70)
        self.assertEqual(slider.value_at(5000), 160)
        self.assertEqual(slider.value_at(slider.track_x + slider.length // 2) % 10, 0)
        slider.set(83)  # not a step: kept as given, inside the limits
        slider.set(500)
        self.assertEqual(variable.get(), 160)
        slider.set(160)  # unchanged: no callback
        self.assertEqual(moved, [83, 160])

    def test_slider_drag_and_wheel(self):
        variable = tk.IntVar(self.root, value=50)
        moved = []
        slider = self.show(Slider(self.frame, variable, 0, 100, 1, length=200, command=moved.append))
        slider.event_generate("<ButtonPress-1>", x=slider.track_x, y=10)
        self.assertEqual(variable.get(), 0)
        slider.event_generate("<B1-Motion>", x=slider.track_x + slider.length, y=10)
        self.assertEqual(variable.get(), 100)
        slider.event_generate("<MouseWheel>", delta=-120)
        self.assertEqual(variable.get(), 99)
        self.assertEqual(moved, [0, 100, 99])

    # --- containers ------------------------------------------------------------------------------

    def test_card_fits_its_contents(self):
        card = self.show(Card(self.frame))
        small = card.winfo_reqheight()
        for i in range(5):
            tk.Label(card.body, text=f"line {i}", bg=ui.CARD).pack()
        self.root.update()
        self.assertGreater(card.winfo_reqheight(), small + 50)
        self.assertTrue(card.find_withtag("background"))

    def test_field_edits_its_variable(self):
        variable = tk.StringVar(self.root, value="2:50")
        field = self.show(Field(self.frame, variable))
        self.assertEqual(field.entry.get(), "2:50")
        field.entry.delete(0, "end")
        field.entry.insert(0, "3:05")
        self.assertEqual(variable.get(), "3:05")

    def test_nav_item(self):
        picked = []
        item = self.show(NavItem(self.frame, ui.ICONS["general"], "General", lambda: picked.append(1)))
        self.click(item, 10, 10)
        self.assertEqual(picked, [1])

    # --- windows chrome --------------------------------------------------------------------------

    def test_window_styling_never_fails(self):
        window = tk.Toplevel(self.root)
        ui.style_window(window)
        window.destroy()
        ui.style_window(window)  # gone already: still no error
        ui.use_dark_menus()
        ui.use_dark_menus()
        menu = tk.Menu(self.root, tearoff=0, **ui.menu_colors())
        menu.add_command(label="x")
        menu.destroy()


if __name__ == "__main__":
    unittest.main()
