"""Python bindings to Odoo's user interface (UI) driven by Selenium."""
import contextlib
import re
import time
import urlparse

from selenium.common.exceptions import NoAlertPresentException
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support import ui

from odooselenium import wait


PAGER_STATUS_REX = re.compile('\d+-(?P<last>\d+)')


class OdooUI9(object):
    """Encapsulate DOM elements of Odoo user interface."""
    def __init__(self, webdriver, base_url='http://localhost:8069'):
        #: Selenium WebDriver instance.
        self.webdriver = webdriver
        #: Base URL of Odoo web service.
        self.base_url = base_url

    @property
    def create_button(self):
        return self.webdriver.find_element(
            By.XPATH,
            "//button["
            "@data-bt-testing-model_name='stock.move' and "
            "@data-bt-testing-name='oe_list_add']")

    def install_module_web_selenium(self):
        """Install module web_selenium using original Odoo's UI.

        Other methods of OdooUI take advantage of features provided by
        web_selenium.

        """

    @contextlib.contextmanager
    def wait_for_page_load(self, timeout=10):
        """Wait for full page load and assert new page has been loaded."""
        # Inspect initial state.
        try:
            initial_body = self.webdriver.find_element(By.XPATH, '//body')
        except NoSuchElementException:  # First load.
            initial_body = None

        # Yield (back to 'with' block, where user triggers page load).
        yield

        # Wait for body to change.
        ui.WebDriverWait(self.webdriver, timeout).until(
            expected_conditions.staleness_of(initial_body)
        )

    @contextlib.contextmanager
    def wait_for_ajax_load(self, timeout=10):
        """Wait for AJAX-style load and assert new page has been loaded."""
        # Inspect initial state.
        initial_jquery_active = not wait.jquery_inactive(self.webdriver)

        # Yield (back to 'with' block where user clicks or whatever)
        yield

        # Check state changed.
        def page_loaded(webdriver):
            # jQuery should be inactive (no AJAX pending).
            if not initial_jquery_active:
                if not wait.jquery_inactive(webdriver):
                    return False
            # Body element doesn't have class 'oe_wait'.
            try:
                webdriver.find_element(By.CSS_SELECTOR, 'body.oe_wait')
            except:
                pass
            else:
                return False
            return True

        ui.WebDriverWait(self.webdriver, timeout).until(page_loaded)

    def login(self, username, password, dbname=None):
        """Log in Odoo.

        If ``dbname`` is None and there are several databases, then the first
        one is automatically selected.

        """
        # Display the first page
        self.webdriver.get(self.url())

        # Fill in database selection form.
        try:
            db_field = self.webdriver.find_element(By.ID, u'db')
        except NoSuchElementException:
            pass
        else:
            with self.wait_for_page_load():
                if dbname:  # Select database by name.
                    ui.Select(db_field).select_by_value(dbname)
                else:  # Select first database available.
                    db_field.send_keys(Keys.DOWN)
                    db_field.send_keys(Keys.TAB)

        # Fill in login form.
        login_field = self.webdriver.find_element(By.ID, u'login')
        login_field.send_keys(username)
        password_field = self.webdriver.find_element(By.ID, u'password')
        password_field.send_keys(password)
        login_button = self.webdriver.find_element(
            By.CSS_SELECTOR,
            '.btn-primary')
        with self.wait_for_page_load():
            login_button.click()

    def url(self, path=''):
        """Return complete URL."""
        return u'{base:s}/{path:s}'.format(
            base=self.base_url,
            path=path.lstrip('/'),
        )

    def list_modules(self):
        xpath = '//a[@class="o_app o_action_app"]/div[@class="o_caption"]'
        modules = self.webdriver.find_elements_by_xpath(xpath)
        return modules

    def go_to_homescreen(self):
        xpath = ('//a[@class="navbar-brand o_menu_toggle"]'
                 '/i[contains(@class, "fa")]')
        try:
            elem = self.webdriver.find_element_by_xpath(xpath)
        except NoSuchElementException:
            return

        if 'fa-th' in elem.get_attribute('class'):
            elem.click()

    def go_to_module(self, module_name, timeout=10):
        """Go to the home screen if necessary, then click on a module."""
        self.go_to_homescreen()
        modules = self.list_modules()
        module_link = None
        for module in modules:
            if module.text == module_name:
                module_link = module
                break
        assert module_link is not None, \
            "Couldn't find module menu '{0}'".format(module_name)
        with self.wait_for_ajax_load():
            module.click()
        # Wait for application view to be loaded.
        ui.WebDriverWait(self.webdriver, timeout).until(
            expected_conditions.presence_of_element_located((
                By.CSS_SELECTOR,
                '.o_content'
            ))
        )

    def go_to_view(self, view_name, timeout=10):
        """Click on the view in menu."""
        xpath = ('//ul[@class="nav navbar-nav o_menu_sections"]/li'
                 '/descendant::*[normalize-space(text())="{}"]')

        menu_parts = view_name.split(u'/')
        for menu_part in menu_parts:
            try:
                elem = self.webdriver.find_element_by_xpath(xpath.format(
                    menu_part))
                with self.wait_for_ajax_load():
                    elem.click()
            except NoSuchElementException:
                raise RuntimeError("Couldn't find view menu '{0}'".format(
                    view_name))

    def switch_to_view(self, view_name):
        """Switch to list, form or kanban view

        @param view_name: should be list, form or kanban"""

        xpath = ('//button[contains(@class, "o_cp_switch_{}") and '
                 '@data-original-title="{}"]'.format(view_name,
                                                     view_name.capitalize()))
        button = self.wait_for_visible_element_by_xpath(xpath)
        button.click()

    def click_form_view_tab(self, tab_name, in_dialog=False):
        if in_dialog:
            xpath = '//div[contains(@class, "modal-body")]'
        else:
            xpath = ''

        xpath += '//a[@role="tab" and normalize-space(text())="{}"]'.format(
            tab_name)
        tab = self.webdriver.find_element_by_xpath(xpath)
        with self.wait_for_ajax_load():
            tab.click()

    def click_button(self, button_name, view_name):
        # TODO: convert to v9
        button_divs = self.webdriver.find_elements_by_css_selector(
            '.oe_view_manager_buttons .oe_{}_buttons'.format(view_name))
        for button_div in button_divs:
            if button_div.is_displayed():
                # Select all the buttons on the div displayed
                buttons = button_div.find_elements_by_tag_name('button')
                # Click on the button requested
                for button in buttons:
                    # Print "Button text: ",button.text
                    if button.text == button_name:
                        with wait.wait_for_body_odoo_load(self.webdriver):
                            button.click()
                        break

    def click_back_button(self, name):
        xpath = '//li[@class="o_back_button"]/a[text()="{}"]'.format(name)
        elem = self.webdriver.find_element_by_xpath(xpath)
        with self.wait_for_ajax_load():
            elem.click()

    def click_edit(self, timeout=10):
        self.click_ajax_load_button('oe_form_button_edit', timeout=timeout)

    def click_apply(self, timeout=10):
        # TODO: test with v9
        self.click_ajax_load_button('execute', timeout=timeout)

    def click_ajax_load_button(self, data_bt_testing_name,
                               data_bt_testing_model_name=None, timeout=10):
        if data_bt_testing_model_name:
            xpath = ('//button[@data-bt-testing-name="{}" and '
                     '@data-bt-testing-model_name="{}"]'.format(
                         data_bt_testing_name, data_bt_testing_model_name))
        else:
            xpath = '//button[@data-bt-testing-name="{}"]'.format(
                    data_bt_testing_name)

        buttons = self.webdriver.find_elements_by_xpath(xpath)
        visible_buttons = [b for b in buttons if b.is_displayed()]
        if len(visible_buttons) != 1:
            raise RuntimeError("Couldn't find exactly one button to click")
        with self.wait_for_ajax_load(timeout):
            visible_buttons[0].click()

    def delete_item_from_form_kanban(self, value, timeout=10):
        # TODO: test with v9
        xpath = ('//a[contains(@class, "oe_kanban_action") and text()="{}"]'
                 '/ancestor::div[contains(@class, "oe_kanban_record")]'
                 '//a[contains(@class, "oe_kanban_action") and '
                 '@data-type="delete"]'.format(value))

        self._delete_item_from_form(xpath, timeout)

    def get_values_from_form_kanban(self):
        """Get the displayed values of a form sub-kanban"""
        # TODO: test with v9

        xpath = ('//div[@class="oe_form"]//div[contains(@class, '
                 '"oe_kanban_record")]//table[@class="oe_kanban_table"]//a')

        elements = self.webdriver.find_elements_by_xpath(xpath)

        return [e.text for e in elements if e.is_displayed()]

    def get_rows_from_form_list(self, header=None):
        """Get the values of all rows on a form sub-list"""

        if header:
            columns_xpath = ('//div[normalize-space(text())="{}"]'
                             '//following-sibling::div[1]//table[@class="'
                             'oe_list_content"]/thead/'
                             'tr[@class="oe_list_header_columns"]/th'
                             .format(header))
        else:
            columns_xpath = ('//div[@class="oe_form"]//table[@class="'
                             'oe_list_content" and not(ancestor::*[@style='
                             '"display: none;"])]/thead'
                             '/tr[@class="oe_list_header_columns"]/th')

        headers_xpath = '{}/div'.format(columns_xpath)

        if header:
            xpath = ('//div[normalize-space(text())="{}"]'
                     '/following-sibling::*[1]//'
                     'table[@class="oe_list_content"]/tbody/tr/td'.format(
                         header))
        else:
            xpath = ('//div[@class="oe_form"]//table[@class="oe_list_content" '
                     'and not(ancestor::*[@style="display: none;"])]/tbody/tr'
                     '/td')

        return self._get_rows_from_list(columns_xpath, headers_xpath, xpath)

    def delete_item_from_form_list(self, column, value, header=None,
                                   timeout=10):
        # TODO: test with v9
        xpath = ('//table[contains(@class, "o_list_view")]/tbody/tr/'
                 'td[@data-field="{}" and text()="{}"]/following-sibling::'
                 'td[@class="o_list_record_delete"]'.format(column, value))

        if header:
            xpath = ('//div[normalize-space(text())="{}"]/'
                     'following-sibling::*[1]{}'.format(header, xpath))

        self._delete_item_from_form(xpath, timeout)

    def _delete_item_from_form(self, xpath, timeout):
        # TODO: test with v9
        delete_buttons = self.webdriver.find_elements_by_xpath(xpath)

        visible_buttons = [b for b in delete_buttons if b.is_displayed()]
        if len(visible_buttons) < 1:
            raise RuntimeError("No delete buttons found")
        for button in visible_buttons:
            with self.wait_for_ajax_load(timeout):
                button.click()
                try:
                    self.webdriver.switch_to.alert.accept()
                except NoAlertPresentException:
                    pass

    def add_item_to_form_kanban(self, timeout=10):
        # TODO: test with v9
        xpath = '//button[@data-bt-testing-button="oe_kanban_button_new"]'
        self._add_item_to_form(xpath, timeout)

    def add_item_to_form_table(self, header=None, timeout=10):
        # TODO: test with v9
        xpath = '//*[@class="o_form_field_x2many_list_row_add"]/a'
        if header:
            xpath = ('//div[normalize-space(text())="{}"]/'
                     'following-sibling::*[1]{}'.format(header, xpath))
        self._add_item_to_form(xpath, timeout)

    def _add_item_to_form(self, xpath, timeout):
        # TODO: test with v9
        add_links = self.webdriver.find_elements_by_xpath(xpath)
        visible_links = [l for l in add_links if l.is_displayed()]
        if len(visible_links) != 1:
            raise RuntimeError("Couldn't find exactly one Add an item link")
        with self.wait_for_ajax_load(timeout):
            visible_links[0].click()

    def get_url_fragments(self, url=None):
        """Return dictionary of current URL fragment.

        As an example, on detail page of invoice,
        ``self.get_url_fragments()['id']`` returns ID of current invoice.

        """
        if url is None:
            url = self.webdriver.current_url
        parsed_url = urlparse.urlparse(url)
        fragment_parts = parsed_url.fragment.split('&')
        fragment_values = {}
        for part in fragment_parts:
            key, value = part.split('=')
            fragment_values[key] = value
        return fragment_values

    def delete_from_list(self):
        """Delete items selected with select_list_items"""
        self.click_more_item('Delete')
        self.webdriver.switch_to.alert.accept()

    def select_list_items(self, data_field, column_value):
        """Select items in a list view where the specified data_field has the
        specified column_value"""

        xpath = ('//table[contains(@class, "o_list_view")]/tbody/tr/'
                 'td[@data-field="{}" and text()="{}"]/../'
                 'td[@class="o_list_record_selector"]/div/input'.format(
                     data_field, column_value))
        checkboxes = self.webdriver.find_elements_by_xpath(xpath)
        for checkbox in checkboxes:
            checkbox.click()

    def get_rows_from_list(self, data_field=None, column_value=None):
        """Get the values of all rows having a specific column value.
        If data_field and column_value are not specified, get all rows."""

        columns_xpath = ('//table[contains(@class, "o_list_view")]/thead/tr'
                         '/th[not(@class="o_list_record_selector")]')

        if data_field and column_value:
            xpath = ('//table[contains(@class, "o_list_view")]/tbody/tr/td['
                     '@data-field="{}" and text()="{}"]/..'
                     '/td[not(@class="o_list_record_selector")]'.format(
                         data_field, column_value))
        else:
            xpath = '//table[contains(@class, "o_list_view")]/tbody/tr/td'

        return self._get_rows_from_list(columns_xpath, xpath)

    def _get_rows_from_list(self, columns_xpath, values_xpath):
        columns = [elem for elem in
                   self.webdriver.find_elements_by_xpath(columns_xpath)
                   if elem.is_displayed()]

        chunk_size = len(columns)

        header_values = [elem.text.strip() for elem in columns if
                         elem.is_displayed()]

        header_values += ['Untitled{}'.format(x) for x
                          in xrange(chunk_size - len(header_values))]
        values = []

        all_values = self.webdriver.find_elements_by_xpath(values_xpath)
        all_values = [v for v in all_values if v.is_displayed()]
        lines = [all_values[i:i + chunk_size] for i in xrange(0,
                                                              len(all_values),
                                                              chunk_size)]
        for line in lines:
            line_values = [elem.text for elem in line]
            values.append(dict(zip(header_values, line_values)))

        return values

    def click_more_item(self, menu_item):
        """Click an item in the More menu that appears when selecting list
        items"""

        action_button = self.wait_for_visible_element_by_xpath(
            '//a[@class="dropdown-toggle" and normalize-space(text())="Action"'
            ' and not(@role="button")]')
        if action_button.is_displayed():
            action_button.click()
            item_link = self.wait_for_visible_element_by_xpath(
                '//ul[@class="dropdown-menu"]/li/a['
                'normalize-space(text())="{}"]'.format(menu_item))
            item_link.click()
        else:
            raise RuntimeError('Action button is not displayed')

    def clear_search_facets(self):
        xpath = ('//div[@class="o_searchview_facet"]'
                 '/div[contains(@class, "o_facet_remove")]')
        try:
            button = self.webdriver.find_element_by_xpath(xpath)
        except NoSuchElementException:
            return
        while button:
            with self.wait_for_ajax_load():
                button.click()
            try:
                button = self.webdriver.find_element_by_xpath(xpath)
            except NoSuchElementException:
                button = None

    def search_for(self, search_string):
        xpath = '//input[@class="o_searchview_input"]'
        input_fields = self.webdriver.find_elements_by_xpath(xpath)
        input_field = next(field for field in input_fields
                           if field.is_displayed())
        with self.wait_for_ajax_load():
            input_field.click()
            input_field.send_keys(search_string)
            input_field.send_keys(Keys.ENTER)

    def click_list_column(self, data_field, value, click_column=None):
        """Click the first item with the specified value in the specified
        column in a list. Cycle through multiple pages if they're available and
        it is necessary.
        If click_column is not specified, find the cell under data_field with
        contains value and click it.
        If click_column is specified, find the cell under data_field which
        contains value, then click click_column in the same row."""

        rows = []
        while not rows:
            rows = self.get_rows_from_list(data_field, value)

            next_button_xpath = ('//div[@class="o_cp_pager"]'
                                 '/div/span[contains(@class, "btn-group")]'
                                 '/button[contains(@class, '
                                 '"fa-chevron-right")]')
            next_buttons = self.webdriver.find_elements_by_xpath(
                next_button_xpath)

            if rows:
                break
            elif not next_buttons:
                raise RuntimeError('Could not find row with {}'.format(value))
            else:
                pager_status_xpath = '//span[@class="o_pager_value"]'
                pager_status = self.webdriver.find_element_by_xpath(
                    pager_status_xpath)

                pager_limit_xpath = '//span[@class="o_pager_limit"]'
                pager_limit = self.webdriver.find_element_by_xpath(
                    pager_limit_xpath)

                match = re.match(PAGER_STATUS_REX, pager_status.text)

                if match:
                    status_match = match.groupdict()
                    if status_match['last'] == pager_limit.text:
                        raise RuntimeError('Could not find row with {}'.format(
                            value))
                with self.wait_for_ajax_load():
                    next_buttons[0].click()

        xpath = ('//table[contains(@class, "o_list_view")]/tbody/tr/'
                 'td[@data-field="{}" and text()="{}"]'.format(
                     data_field, value))

        attempts = 2
        elem = None
        counter = 0
        while not elem and counter < attempts:
            elems = self.webdriver.find_elements_by_xpath(xpath)
            try:
                elem = next(e for e in elems if e.is_displayed())
            except StopIteration:
                counter += 1
                time.sleep(10)
        if not elem:
            raise RuntimeError('Could not find row with {}'.format(value))

        if click_column:
            elem = elem.find_element(by='xpath',
                                     value='following-sibling::td['
                                     '@data-field="{}"]'.format(click_column))

        with self.wait_for_ajax_load():
            elem.click()

    def enable_developer_mode(self):
        """Enable developer mode."""

        self.open_user_menu()
        self.click_user_menu_item('About')
        xpath = '//a[@href="?debug"]'
        elem = self.wait_for_visible_element_by_xpath(xpath)
        with wait.wait_for_new_page_load(self.webdriver):
            elem.click()

    def open_user_menu(self):
        """Open the user dropdown menu"""

        xpath = '//span[@class="oe_topbar_name"]'
        menu = self.wait_for_visible_element_by_xpath(xpath)
        menu.click()

    def click_user_menu_item(self, item):
        """Click an item in the user drop down menu. The menu has to be opened
        first."""

        xpath = ('//ul[@class="dropdown-menu"]/li'
                 '/a[normalize-space(text())="{}"]'.format(item))
        elem = self.wait_for_visible_element_by_xpath(xpath)
        with self.wait_for_ajax_load():
            elem.click()

    def install_module(self, module_name, column='name', timeout=60,
                       upgrade=False):
        """ Install the specified module. You need to be on the Settings page.
        This will NOT go through the setup wizard.

        @param module_name: the name of the module
        @param column: in which column to find the module_name. The default
                       (shortdesc) is the human-readable description.
        @param timeout: max. seconds to wait for module installation
        @param upgrade: whether to click the upgrade button if the module is
                        already installed"""

        with self.wait_for_ajax_load():
            self.switch_to_view('list')

        self.clear_search_facets()
        self.search_for(module_name)
        row_data = self.get_rows_from_list(column, module_name)
        if row_data[0]['Status'] == 'Installed' and upgrade is False:
            return

        self.click_list_column(column, module_name)
        btn = self.wait_for_visible_element_by_xpath(
            '//button[@class="btn btn-sm btn btn-primary"]')
        with self.wait_for_ajax_load(timeout):
            btn.click()

    def _get_bt_testing_element(self, field_name, model_name=None, data=None,
                                in_dialog=False, last=False):
        if in_dialog:
            xpath = '//div[@class="modal-content"]'
        else:
            xpath = ''

        if model_name:
            xpath = ('{}//*[@data-bt-testing-name="{}" and '
                     '@data-bt-testing-model_name="{}"]'.format(xpath,
                                                                field_name,
                                                                model_name))
        else:
            xpath = '{}//*[@data-bt-testing-name="{}"]'.format(xpath,
                                                               field_name)

        if data:
            for key, value in data.iteritems():
                xpath = re.sub(
                    ']$', ' and translate(@{}, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
                    '"abcdefghijklmnopqrstuvwxyz")="{}"]'.format(
                        key, value.lower()),
                    xpath)

        if last:
            xpath = '({})[last()]'.format(xpath)

        return self.wait_for_visible_element_by_xpath(xpath)

    def write_in_element(self, field_name, model_name, text, clear=True,
                         in_dialog=False):
        """Writes text to an element
        @param field_name: data-bt-testing-name on the element
        @param model_name: the data-bt-testing-model_name on the element
        @param text: text to enter into the field
        @clear: whether to clear the field first
        @param clear: whether to clear the field first
        """
        elem = self._get_bt_testing_element(field_name, model_name,
                                            in_dialog=in_dialog)

        if clear:
            elem.clear()

        elem.send_keys(text)

    def toggle_checkbox(self, field_name, model_name):
        """Toggles a checkbox"""
        # _get_bt_testing_element waits for the element to be visible, but
        # checkboxes have opacity set to 0 in v9.
        elem = self.webdriver.find_element_by_xpath(
            '//input[@type="checkbox" and @data-bt-testing-model_name="{}" '
            'and @data-bt-testing-name="{}"]'.format(model_name, field_name))
        if elem.find_element_by_xpath('parent::div').is_displayed:
            elem.click()
        else:
            raise NoSuchElementException(
                'Could not find checkbox for {}.{}'.format(model_name,
                                                           field_name))

    def open_text_dropdown(self, field_name, model_name, in_dialog):
        """Open a dropdown list on a text field"""

        if in_dialog:
            xpath = '//div[@class="modal-content"]'
        else:
            xpath = ''

        xpath += ('//input[@data-bt-testing-name="{}" and '
                  '@data-bt-testing-model_name="{}"]/parent::'
                  'div[@class="o_form_input_dropdown"]'.format(field_name,
                                                               model_name))
        elem = self.wait_for_visible_element_by_xpath(xpath)
        elem.click()
        time.sleep(0.5)

    def get_value(self, field, model):
        """Get the value of a field"""

        field = self._get_bt_testing_element(field, model)
        if field.get_attribute('type') == 'checkbox':
            return field.is_selected()
        elif field.tag_name == 'select':
            field = ui.Select(field)
            return field.first_selected_option.text
        else:
            return field.get_attribute('value')

    def enter_data(self, field, model, data, clear=True, search_column=None,
                   in_dialog=False):
        """Enter data into a field. The type of field will be determined.

        @param field: the data-bt-testing-name attribute for the field
        @param model: the data-bt-testing-model_name attribute for the field
        @param data: the data to enter
        @param search_column: the column title to search in the Search form in
                              case of an autocomplete text field
        """
        if data in [True, False]:
            input_field = self.webdriver.find_element_by_xpath(
                '//input[@type="checkbox" and @data-bt-testing-model_name="{}"'
                ' and @data-bt-testing-name="{}"]'.format(model, field))
            if not input_field.find_element_by_xpath(
                    'parent::div').is_displayed:
                raise RuntimeError('Checkbox is not displayed')
        else:
            input_field = self._get_bt_testing_element(field, model,
                                                       in_dialog=in_dialog)

        if input_field.tag_name == 'select':
            dropdown_xpath = ('//select[@data-bt-testing-name="{}" and '
                              '@data-bt-testing-model_name="{}"]/'
                              'option[normalize-space('
                              'text())="{}"]'.format(field, model, data))
            input_field = self.webdriver.find_element_by_xpath(dropdown_xpath)
            input_field.click()
        elif input_field.tag_name == 'input':
            elem_class = input_field.get_attribute('class')
            elem_type = input_field.get_attribute('type')
            if (elem_type == 'text' and
                    'ui-autocomplete-input' in elem_class):
                if isinstance(data, list):
                    self.create_from_text_dropdown(field, model, in_dialog,
                                                   data)
                else:
                    if data == '':
                        field = self._get_bt_testing_element(field, model)
                        field.clear()
                    else:
                        self.search_text_dropdown(field, model, search_column,
                                                  data, in_dialog)
            elif (elem_type in ['text', 'password'] and
                    (any(x in elem_class for x in ['o_form_input',
                                                   'oe_datepicker_master'])
                     or elem_class == '')):
                self.write_in_element(field, model, data, clear, in_dialog)
            elif elem_type == 'checkbox':
                if input_field.is_selected() != data:
                    self.toggle_checkbox(field, model)
            elif elem_type == 'radio':
                elem = self._get_bt_testing_element(field, model,
                                                    {'value': data},
                                                    in_dialog=in_dialog)
                elem.click()
            else:
                raise NotImplementedError(
                    "I don't know how to handle {}".format(field))
        elif input_field.tag_name == 'textarea':
            self.write_in_element(field, model, data, clear, in_dialog)

    def wizard_screen(self, config_data, next_button="action_next",
                      timeout=30):
        """Enter the specified config data in the wizard screen.
        config_data is a list of dicts. Each dict needs:
            * field: the data-bt-testing-name attribute for the field
            * model: the data-bt-testing-model_name attribute for the field
            * value: the value to enter
            * search_column: the column title to search in the Search form in
                             case of an autocomplete text field
        """
        for config_item in config_data:
            if config_item.get('tab'):
                self.click_form_view_tab(config_item['tab'], True)
            self.enter_data(config_item['field'], config_item['model'],
                            config_item['value'],
                            config_item.get('clear', True),
                            config_item.get('search_column'), True)

        # TODO: buttons on modal dialogs don't work - this is an issue
        #       with web_selenium that I was unable to solve.
        #       Working around it like this.
        button = self.wait_for_visible_element_by_xpath(
            '//button[contains(@class, "btn-primary")]/span[text() = "Save"]'
            '/parent::button')
        with self.wait_for_ajax_load(timeout):
            button.click()

    def _get_data_id_from_column_title(self, column_title):
        """Get the data-id attribute based on a column title"""

        xpath = ('//table[contains(@class, "o_list_view table")]/thead/tr'
                 '/th[normalize-space(text())="{}"]'.format(column_title))

        elems = self.webdriver.find_elements_by_xpath(xpath)
        for elem in elems:
            if elem.is_displayed():
                return elem.get_attribute('data-id')
        raise NoSuchElementException("Couldn't find data-id for column {}"
                                     .format(column_title))

    def _get_autocomplete_dropdown_items(self, field_name, model, in_dialog):
        self.open_text_dropdown(field_name, model, in_dialog)
        menu_items_xpath = ('//ul[contains(@class, "ui-autocomplete")]/'
                            'li[contains(@class, "ui-menu-item")]/a')
        menu_items = self.webdriver.find_elements_by_xpath(menu_items_xpath)

        return menu_items

    def search_text_dropdown(self, field_name, model, column_title, value,
                             in_dialog):
        """Search through a text dropdown. If the value is already in the
        dropdown, click it. If not, go to the search form via the Search
        More... item."""

        menu_items = self._get_autocomplete_dropdown_items(field_name,
                                                           model,
                                                           in_dialog)
        try:
            elem = next(e for e in menu_items if e.text == value)
            elem.click()
            return
        except StopIteration:
            self._search_more(menu_items, column_title, value)

    def create_from_text_dropdown(self, field_name, model, in_dialog,
                                  config_data):
        """Create a new item in an autocomplete text field via the Create and
        Edit option"""
        menu_items = self._get_autocomplete_dropdown_items(field_name,
                                                           model,
                                                           in_dialog)
        elem = next(e for e in menu_items if e.text == 'Create and Edit...')
        with self.wait_for_ajax_load():
            elem.click()
        self.wizard_screen(config_data,
                           next_button="oe_form_button_save_and_close")

    def _search_more(self, menu_items, column_title, value):
        """Search for an element in an autocomplete text field via the Search
        More option.

        @param menu_items: a list of the menu items in the dropdown
        @param column_title: the title of the column in which to search in the
                             subsequent dialog
        @param value: the value to search for
        """
        elem = next(e for e in menu_items if e.text == 'Search More...')
        with self.wait_for_ajax_load():
            elem.click()
        search_field = self._get_data_id_from_column_title(column_title)
        with self.wait_for_ajax_load():
            self.click_list_column(search_field, value)

    def wait_for_visible_element_by_xpath(self, xpath, timeout=10, attempts=2):
        """Find an element by XPath and wait until it is visible. Will try up
        to <attempts> times with a timeout of <timeout> seconds each time."""

        tries = 0
        elem = None

        while tries < attempts and elem is None:
            try:
                condition = expected_conditions.visibility_of_element_located(
                    (By.XPATH, xpath))
                elem = ui.WebDriverWait(self.webdriver,
                                        timeout).until(condition)
            except TimeoutException:
                tries += 1
                if tries == attempts:
                    raise

        return elem
