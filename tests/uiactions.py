
# Copyright 2009-2017 Jaap Karssenberg <jaap.karssenberg@gmail.com>



import tests

from tests.mainwindow import setUpMainWindow

import os
from gi.repository import Gtk

from zim.errors import Error
from zim.newfs import LocalFolder
from zim.notebook import get_notebook_list, Path, Page, NotebookInfo
from zim.notebook.notebook import NotebookConfig
from zim.formats import ParseTree
from zim.gui.clipboard import Clipboard

import zim.gui


from zim.gui.uiactions import UIActions, PAGE_EDIT_ACTIONS, TrashPageDialog, DeletePageDialog

def strip_file_url_prefix(str):
	if str.startswith('file://'): return str[7:]
	return str


class EmptyWindowObject(object):
	# Any other method than get_toplevel() should raise to prevent
	# unauthorized access to the MainWindow object

	def get_toplevel(self):
		return None


class TestUIActions(tests.TestCase):

	def setUp(self):
		window = EmptyWindowObject()
		self.notebook = self.setUpNotebook(
			content={
				'Test': 'Test 123\n',
				'ExistingPage': 'Exists !\n'
			}
		)
		self.page = self.notebook.get_page(Path('Test'))
		self.navigation = tests.MockObject(methods=('open_page', 'open_notebook', 'open_manual'))
		self.uiactions = UIActions(
			window,
			self.notebook,
			self.page,
			self.navigation,
		)

	def testCreateNewPage(self):
		page = self.notebook.get_page(Path('NewPage'))
		self.assertFalse(page.exists())

		def open_new_page(dialog):
			dialog.set_input(page='NewPage')
			dialog.assert_response_ok()

		with tests.DialogContext(open_new_page):
			self.uiactions.new_page()

		self.assertTrue(page.exists())
		self.assertEqual(self.navigation.lastMethodCall, ('open_page', page))

	def testCreateNewPageFailsForExistingPage(self):
		from zim.notebook import PageExistsError

		def open_new_page(dialog):
			dialog.set_input(page='ExistingPage')
			self.assertRaises(PageExistsError, dialog.assert_response_ok)

		with tests.DialogContext(open_new_page):
			self.uiactions.new_page()

	def testCreateNewPageImportExistingTextFile(self):
		# See also mainwindow.TestOpenPageImportTextFile
		file = self.notebook.folder.file('ExistingFile.txt')
		file.write('Test 123') # Not a page, just text!

		def open_new_page(dialog):
			dialog.set_input(page='ExistingFile')
			dialog.assert_response_ok()

		def do_import(questiondialog):
			questiondialog.answer_yes()

		with tests.DialogContext(open_new_page, do_import):
			self.uiactions.new_page()

		lines = file.readlines()
		self.assertEqual(lines[0], 'Content-Type: text/x-zim-wiki\n')
		self.assertEqual(lines[-1], 'Test 123\n')

	def testCreateNewPageWithRelativePaths(self):
		self.uiactions.page = self.notebook.get_page(Path('Test:SubPage'))

		for string, result in (
			('NewPage', Path('Test:NewPage')),
			(':NewPage', Path('NewPage')),
			('+NewPage', Path('Test:SubPage:NewPage')),
		):
			page = self.notebook.get_page(result)
			self.assertFalse(page.exists())

			def open_new_page(dialog):
				dialog.set_input(page=string)
				dialog.assert_response_ok()

			with tests.DialogContext(open_new_page):
				self.uiactions.new_page()

			self.assertTrue(page.exists())
			self.assertEqual(self.navigation.lastMethodCall, ('open_page', page))

	def testCreateNewChildPage(self):
		page = self.notebook.get_page(Path('Test:Child'))
		self.assertFalse(page.exists())

		def open_new_page(dialog):
			dialog.set_input(page='Child')
			dialog.assert_response_ok()

		with tests.DialogContext(open_new_page):
			self.uiactions.new_sub_page()

		self.assertTrue(page.exists())
		self.assertEqual(self.navigation.lastMethodCall, ('open_page', page))

	def testOpenAnotherNotebook(self):
		from zim.gui.notebookdialog import NotebookDialog

		def check_dialog_shown(dialog):
			assert isinstance(dialog, NotebookDialog)

		with tests.DialogContext(check_dialog_shown):
			self.uiactions.show_open_notebook()

		# See tests/notebookdialog.py for more testing of the dialog itself

	def testImportPageFromFile(self):
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('TestImport.txt')
		file.write('import test 123\n')

		def import_file(dialog):
			dialog.set_file(file)
			dialog.assert_response_ok()

		with tests.DialogContext(import_file):
			self.uiactions.import_page()

		page = self.notebook.get_page(Path('TestImport'))
		self.assertTrue(page.exists())
		self.assertEqual(page.dump('plain'), ['import test 123\n'])

	def testOpenNewWindow(self):
		self.uiactions.widget = setUpMainWindow(self.notebook)

		def pagewindow(window):
			window.pageview.page == self.page

		with tests.DialogContext(pagewindow):
			self.uiactions.open_new_window()

	def testOpenNewWindowWithPage(self):
		self.uiactions.widget = setUpMainWindow(self.notebook)

		page = self.notebook.get_page(Path('OtherPage'))
		self.assertNotEqual(page, self.page)

		def pagewindow(window):
			window.pageview.page == page

		with tests.DialogContext(pagewindow):
			self.uiactions.open_new_window(page)

	def testSaveCopyDialog(self):
		folder = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		file = folder.file('test.txt')

		def savecopy(dialog):
			dialog.set_file(file)
			dialog.assert_response_ok()

		with tests.DialogContext(savecopy):
			self.uiactions.save_copy()

		self.assertEqual(file.read(), 'Test 123\n')

	def testShowExport(self):
		from zim.gui.exportdialog import ExportDialog

		def check_dialog_shown(dialog):
			assert isinstance(dialog, ExportDialog)

		with tests.DialogContext(check_dialog_shown):
			self.uiactions.show_export()

		# See tests/export.py for more testing of the dialog itself

	def testEmailPage(self):
		def check_url(widget, url):
			self.assertEqual(url, 'mailto:?subject=Test&body=Test%20123%0A')

		self.uiactions.email_page(_callback=check_url)

	def testRenamePage(self):
		def renamepage(dialog):
			self.assertEqual(dialog.path, self.page)
			self.assertFalse(dialog.get_input('update'))
			self.assertFalse(dialog.get_input_enabled('update'))
			self.assertFalse(dialog.get_input('head')) # no matching heading
			dialog.set_input(name='NewName')
			dialog.assert_response_ok()

		with tests.DialogContext(renamepage):
			self.uiactions.move_page()

		page = self.notebook.get_page(Path('Test'))
		self.assertFalse(page.exists())
		page = self.notebook.get_page(Path('NewName'))
		self.assertTrue(page.exists())

	def testRenamePageSameNameInvalidInput(self):
		self.assertEqual(self.page.basename, 'Test')

		def renamepage(dialog):
			dialog.set_input(name='Test')
			self.assertFalse(dialog.do_response_ok())

		with tests.DialogContext(renamepage):
			self.uiactions.move_page()

	def testRenamePageFailsForExistingPage(self):
		from zim.notebook import PageExistsError

		def renamepage(dialog):
			dialog.set_input(name='ExistingPage')
			self.assertRaises(PageExistsError, dialog.do_response_ok)

		with tests.LoggingFilter('zim', 'Page already exists'):
			with tests.DialogContext(renamepage):
				self.uiactions.move_page()

	def testRenamePageNonExistingPageFails(self):
		from zim.notebook import PageNotFoundError
		page = self.notebook.get_page(Path('NonExistingPage'))

		def renamepage(dialog):
			dialog.set_input(name='NewName')
			self.assertRaises(PageNotFoundError, dialog.do_response_ok)

		with tests.LoggingFilter('zim', 'No such page'):
			with tests.DialogContext(renamepage):
				self.uiactions.move_page(page)

	def testRenamePageWithPageUpdateHeading(self):
		page = self.notebook.get_page(Path('MyPage'))
		page.parse('wiki', ['======= MyPage =======\n', 'Test 123\n'])
		tree = page.get_parsetree()
		self.assertEqual(tree.get_heading_text(), 'MyPage')
		self.notebook.store_page(page)

		def renamepage(dialog):
			self.assertEqual(dialog.path, page)
			self.assertTrue(dialog.get_input('head')) # dialog should detect matching heading
			dialog.set_input(name='NewName')
			dialog.assert_response_ok()

		with tests.DialogContext(renamepage):
			self.uiactions.move_page(page)

		page = self.notebook.get_page(Path('NewName'))
		tree = page.get_parsetree()
		self.assertEqual(tree.get_heading_text(), 'NewName')

	def testRenamePageWithPageKeepHeading(self):
		page = self.notebook.get_page(Path('MyPage'))
		page.parse('wiki', ['======= MyPage =======\n', 'Test 123\n'])
		tree = page.get_parsetree()
		self.assertEqual(tree.get_heading_text(), 'MyPage')
		self.notebook.store_page(page)

		def renamepage(dialog):
			self.assertEqual(dialog.path, page)
			self.assertTrue(dialog.get_input('head')) # dialog should detect matching heading
			dialog.set_input(name='NewName', head=False)
			dialog.assert_response_ok()

		with tests.DialogContext(renamepage):
			self.uiactions.move_page(page)

		page = self.notebook.get_page(Path('NewName'))
		tree = page.get_parsetree()
		self.assertEqual(tree.get_heading_text(), 'MyPage')

	def testRenamePageAddHeading(self):
		# Default test page does not have an heading
		tree = self.page.get_parsetree()
		self.assertEqual(tree.get_heading_text(), '')

		def renamepage(dialog):
			dialog.set_input(name='NewName', head=True)
			dialog.assert_response_ok()

		with tests.DialogContext(renamepage):
			self.uiactions.move_page()

		page = self.notebook.get_page(Path('NewName'))
		tree = page.get_parsetree()
		self.assertEqual(tree.get_heading_text(), 'NewName')

	def testRenamePageUpdateLinks(self):
		referrer = self.notebook.get_page(Path('Referrer'))
		referrer.parse('wiki', 'Test [[Test]]\n')
		self.notebook.store_page(referrer)

		def renamepage(dialog):
			self.assertTrue(dialog.get_input_enabled('update'))
			self.assertTrue(dialog.get_input('update'))
			dialog.set_input(name='NewName')
			dialog.assert_response_ok()

		with tests.DialogContext(renamepage):
			self.uiactions.move_page()

		self.assertEqual(referrer.dump('wiki'), ['Test [[NewName]]\n'])

	def testRenamePageNoUpdateLinks(self):
		referrer = self.notebook.get_page(Path('Referrer'))
		referrer.parse('wiki', 'Test [[Test]]\n')
		self.notebook.store_page(referrer)

		def renamepage(dialog):
			self.assertTrue(dialog.get_input_enabled('update'))
			self.assertTrue(dialog.get_input('update'))
			dialog.set_input(name='NewName', update=False)
			dialog.assert_response_ok()

		with tests.DialogContext(renamepage):
			self.uiactions.move_page()

		self.assertEqual(referrer.dump('wiki'), ['Test [[Test]]\n'])

	def testMovePage(self):
		def movepage(dialog):
			self.assertEqual(dialog.path, self.page)
			self.assertFalse(dialog.get_input('update'))
			self.assertFalse(dialog.get_input_enabled('update'))
			dialog.set_input(parent='ExistingPage')
			dialog.assert_response_ok()

		with tests.DialogContext(movepage):
			self.uiactions.move_page()

		page = self.notebook.get_page(Path('Test'))
		self.assertFalse(page.exists())
		page = self.notebook.get_page(Path('ExistingPage:Test'))
		self.assertTrue(page.exists())

	def testMovePageNonExistingParentOK(self):
		page = self.notebook.get_page(Path('NonExistingPage'))
		self.assertFalse(page.exists())

		def movepage(dialog):
			dialog.set_input(parent='NonExistingPage')
			dialog.assert_response_ok()

		with tests.DialogContext(movepage):
			self.uiactions.move_page()

		page = self.notebook.get_page(Path('Test'))
		self.assertFalse(page.exists())
		page = self.notebook.get_page(Path('NonExistingPage:Test'))
		self.assertTrue(page.exists())

	def testMovePageToTopWithPage(self):
		page = self.notebook.get_page(Path('SomeParent:MyPage'))
		page.parse('wiki', 'test 123\n')
		self.notebook.store_page(page)

		def movepage(dialog):
			dialog.set_input(parent=':')
			dialog.assert_response_ok()

		with tests.DialogContext(movepage):
			self.uiactions.move_page(page)

		page = self.notebook.get_page(Path('SomeParent:MyPage'))
		self.assertFalse(page.exists())
		page = self.notebook.get_page(Path('MyPage'))
		self.assertTrue(page.exists())

	def testMovePageSameParentInvalidInput(self):
		page = self.notebook.get_page(Path('SomeParent:MyPage'))
		page.parse('wiki', 'test 123\n')
		self.notebook.store_page(page)

		def movepage(dialog):
			dialog.set_input(parent='SomeParent')
			self.assertFalse(dialog.do_response_ok())

		with tests.DialogContext(movepage):
			self.uiactions.move_page(page)

	def testMovePageFailsForExistingPage(self):
		from zim.notebook import PageExistsError

		page = self.notebook.get_page(Path('SomeParent:ExistingPage'))
		page.parse('wiki', 'test 123\n')
		self.notebook.store_page(page)

		def movepage(dialog):
			dialog.set_input(parent=':')
			self.assertRaises(PageExistsError, dialog.do_response_ok)

		with tests.LoggingFilter('zim', 'Page already exists'):
			with tests.DialogContext(movepage):
				self.uiactions.move_page(page)

	def testMovePageFailsForExistingTextFile(self):
		from zim.notebook import PageNotAvailableError
		file = self.notebook.folder.file('ExistingFile.txt')
		file.write('Test 123') # Not a page, just text!

		page = self.notebook.get_page(Path('SomeParent:ExistingFile'))
		page.parse('wiki', 'test 123\n')
		self.notebook.store_page(page)

		def movepage(dialog):
			dialog.set_input(parent=':')
			self.assertRaises(PageNotAvailableError, dialog.do_response_ok)

		with tests.LoggingFilter('zim', 'Page not available'):
			with tests.DialogContext(movepage):
				self.uiactions.move_page(page)

	def testMovePageNonExistingPageFails(self):
		from zim.notebook import PageNotFoundError
		page = self.notebook.get_page(Path('NonExistingPage'))

		def movepage(dialog):
			dialog.set_input(parent='NewParent')
			self.assertRaises(PageNotFoundError, dialog.do_response_ok)

		with tests.LoggingFilter('zim', 'No such page'):
			with tests.DialogContext(movepage):
				self.uiactions.move_page(page)

	def testMovePageUpdateLinks(self):
		referrer = self.notebook.get_page(Path('Referrer'))
		referrer.parse('wiki', 'Test [[Test]]\n[[#anchor]]\n')
		self.notebook.store_page(referrer)

		def movepage(dialog):
			self.assertTrue(dialog.get_input_enabled('update'))
			self.assertTrue(dialog.get_input('update'))
			dialog.set_input(parent='NewParent')
			dialog.assert_response_ok()

		with tests.DialogContext(movepage):
			self.uiactions.move_page()

		self.assertEqual(referrer.dump('wiki'), ['Test [[NewParent:Test]]\n', '[[#anchor]]\n'])

	def testMovePageNoUpdateLinks(self):
		referrer = self.notebook.get_page(Path('Referrer'))
		referrer.parse('wiki', 'Test [[Test]]\n')
		self.notebook.store_page(referrer)

		def movepage(dialog):
			self.assertTrue(dialog.get_input_enabled('update'))
			self.assertTrue(dialog.get_input('update'))
			dialog.set_input(parent='NewParent', update=False)
			dialog.assert_response_ok()

		with tests.DialogContext(movepage):
			self.uiactions.move_page()

		self.assertEqual(referrer.dump('wiki'), ['Test [[Test]]\n'])

	def testEditProperties(self):
		from zim.gui.propertiesdialog import PropertiesDialog
		self.uiactions.widget = Gtk.Window()

		with tests.DialogContext(
			(PropertiesDialog, lambda d: d.set_input(home='NewHome', document_root='../my_rel_root'))
		):
			self.uiactions.show_properties()

		self.assertEqual(self.notebook.config['Notebook']['home'], Path('NewHome'))
		self.assertEqual(self.notebook.get_home_page(), Path('NewHome'))
		self.assertEqual(self.notebook.config['Notebook']['document_root'], '../my_rel_root')
		self.assertEqual(self.notebook.document_root, LocalFolder(self.notebook.folder.parent().folder('my_rel_root').path))

	def testEditPropertiesReadOnly(self):
		from zim.gui.propertiesdialog import PropertiesDialog
		self.uiactions.widget = Gtk.Window()

		self.assertFalse(self.notebook.readonly) # implies attribute exists ..
		self.notebook.readonly = True

		with tests.DialogContext(
			(PropertiesDialog, lambda d: self.assertFalse(d.get_input_enabled('home')))
		):
			self.uiactions.show_properties()

	def testPropertiesNotChangedOnCancel(self):
		from zim.gui.propertiesdialog import PropertiesDialog
		self.uiactions.widget = Gtk.Window()

		# In fact this is testig the "cancel" button for all dialogs
		# which have one ..
		def edit_properties(dialog):
			assert isinstance(dialog, PropertiesDialog)
			dialog.set_input(home='NewHome')
			dialog.do_response_cancel()

		with tests.DialogContext(edit_properties):
			self.uiactions.show_properties()

		self.assertNotEqual(self.notebook.config['Notebook']['home'], Path('NewHome'))

	def testCopyLocation(self):
		from zim.gui.clipboard import Clipboard

		Clipboard.set_text('XXX')
		self.assertEqual(Clipboard.get_text(), 'XXX')

		self.uiactions.copy_location()
		self.assertEqual(Clipboard.get_text(), 'Test')

	def testShowTemplateEditor(self):
		from zim.gui.templateeditordialog import TemplateEditorDialog
		with tests.DialogContext(TemplateEditorDialog):
			self.uiactions.show_templateeditor()

		# More tests in tests/templateeditordialog.py

	def testShowPreferencesDialog(self):
		from zim.gui.preferencesdialog import PreferencesDialog
		from zim.plugins import PluginManager

		self.uiactions.widget = Gtk.Window()

		with tests.DialogContext(PreferencesDialog):
			self.uiactions.show_preferences()

		# More tests in tests/preferencesdialog.py

	def testShowSearchDialog(self):
		from zim.gui.searchdialog import SearchDialog

		with tests.DialogContext(SearchDialog):
			self.uiactions.show_search()

		# More tests of dialog function in tests/searchdialog.py

	@tests.expectedFailure # query given after present(), also check callback logic
	def testSearchSection(self):
		from zim.gui.searchdialog import SearchDialog

		for name, text in (
			(self.page.name + ':Child1', 'Test 123'),
			(self.page.name + ':Child2', 'Test 123'),
		):
			page = self.notebook.get_page(Path(name))
			page.parse('plain', text)
			self.notebook.store_page(page)

		def check_section(dialog):
			results = dialog.results_treeview.get_model()
			self.assertEqual(len(results), 2)
			for row in results:
				self.assertTrue(row[-1].ischild(self.page))
			dialog.assert_response_ok()

		with tests.DialogContext(check_section):
			self.uiactions.show_search_section()

	@tests.expectedFailure # query given after present(), also check callback logic
	def testSearchBacklinks(self):
		from zim.gui.searchdialog import SearchDialog

		for name, text in (
			('link1', '[[%s]]\n' % self.page.name),
			('link2', '[[%s]]\n' % self.page.name),
		):
			page = self.notebook.get_page(Path(name))
			page.parse('wiki', text)
			self.notebook.store_page(page)

		def check_backlinks(dialog):
			results = dialog.results_treeview.get_model()
			self.assertEqual(len(results), 2)
			for row in results:
				self.assertIn(row[-1].name, ('link1', 'link2'))
			dialog.assert_response_ok()

		with tests.DialogContext(check_backlinks):
			self.uiactions.show_search_backlinks()

	def testShowRecentChangesDialog(self):

		def use_recent_changes(dialog):
			# Check view
			model = dialog.treeview.get_model()
			pages = set(r[0] for r in model)
			self.assertEqual(pages, {'Test', 'ExistingPage'})

			# TODO: how can we check rendering of date column ?

			# Check live update
			page = self.notebook.get_page(Path('NewPage'))
			page.parse('wiki', 'TEst 123')
			self.notebook.store_page(page)

			pages = set(r[0] for r in model)
			self.assertEqual(pages, {'NewPage', 'Test', 'ExistingPage'})

			# Check opening a page
			col = dialog.treeview.get_column(0)
			dialog.treeview.row_activated(Gtk.TreePath((0,)), col)

		with tests.DialogContext(use_recent_changes):
			self.uiactions.show_recent_changes()

		# self.assertEqual(self.navigation.lastMethodCall, ('open_page', Path('NewPage'))) # FIXME: fails at random in automated tests

	def testShowServerDialog(self):
		application = tests.MockObject(methods=('add_window',))
		window = tests.MockObject(return_values={'get_application': application})
		self.uiactions.widget = tests.MockObject(return_values={'get_toplevel': window})

		from zim.gui.server import ServerWindow
		ServerWindow.show_all = tests.CallBackLogger()

		self.uiactions.show_server_gui()

		self.assertTrue(ServerWindow.show_all.hasBeenCalled)
		self.assertEqual(application.lastMethodCall[0], 'add_window')
		self.assertIsInstance(application.lastMethodCall[1], ServerWindow)

	def testReloadIndex(self):
		self.uiactions.check_and_update_index()

	def testReloadIndexWhileOngoing(self):
		from zim.notebook.operations import ongoing_operation
		from zim.notebook.index import IndexCheckAndUpdateOperation

		op = IndexCheckAndUpdateOperation(self.notebook)
		op_iter = iter(op)
		next(op_iter)
		self.assertEqual(ongoing_operation(self.notebook), op)

		self.uiactions.check_and_update_index()

		self.assertIsNone(ongoing_operation(self.notebook))

	def testEnsureIndexWhileOutOfDate(self):
		self.notebook.index.flush()
		self.assertTrue(self.uiactions.ensure_index_uptodate())

	def testShowManageCustomTools(self):
		from zim.gui.customtools import CustomToolManagerDialog
		with tests.DialogContext(CustomToolManagerDialog):
			self.uiactions.manage_custom_tools()

		# more tests in tests/customtools.py

	def testOpenHelp(self, page=None):
		self.uiactions.show_help()
		self.assertEqual(self.navigation.lastMethodCall, ('open_manual', None))

	def testOpenHelpFAQ(self):
		self.testOpenHelp(page='FAQ')

	def testOpenHelpKeys(self):
		self.testOpenHelp(page='Help:Key Bindings')

	def testOpenHelpBugs(self):
		self.testOpenHelp(page='Bugs')

	def testOpenAboutDialog(self):
		from zim.gui.uiactions import MyAboutDialog
		MyAboutDialog.run = tests.CallBackLogger()
		self.uiactions.show_about()
		self.assertTrue(MyAboutDialog.run.hasBeenCalled)

	def testAccesActionsFromPopupMenu(self):
		# Test depends on first menu item being "new_page_here"
		from zim.gui.uiactions import NewPageDialog
		menu = Gtk.Menu()
		self.uiactions.populate_menu_with_actions(PAGE_EDIT_ACTIONS, menu)

		def open_new_page(dialog):
			self.assertIsInstance(dialog, NewPageDialog)
			dialog.set_input(page='Child')
			dialog.assert_response_ok()

		with tests.DialogContext(open_new_page):
			menu.get_children()[0].activate()

	def testAccesActionsFromPopupMenuForRoot(self):
		# Test depends on first menu item being "new_page_here"
		# When triggered from empty space in index, page will be root namespace
		from zim.gui.uiactions import NewPageDialog
		menu = Gtk.Menu()
		self.uiactions.page = Path(':')
		self.uiactions.populate_menu_with_actions(PAGE_EDIT_ACTIONS, menu)

		def open_new_page(dialog):
			self.assertIsInstance(dialog, NewPageDialog)
			dialog.set_input(page='Child')
			dialog.assert_response_ok()

		with tests.DialogContext(open_new_page):
			menu.get_children()[0].activate()


@tests.slowTest
class TestUIActionsRealFile(tests.TestCase):

	def setUp(self):
		window = EmptyWindowObject()
		self.notebook = self.setUpNotebook(
			mock=tests.MOCK_ALWAYS_REAL,
			content={'Test': 'Test 123'}
		)
		self.page = self.notebook.get_page(Path('Test'))
		self.navigation = tests.MockObject(methods=('open_page', 'open_notebook'))
		self.uiactions = UIActions(
			window,
			self.notebook,
			self.page,
			self.navigation,
		)

	def testTrashPage(self):
		self.assertTrue(self.page.exists())

		with tests.DialogContext(TrashPageDialog):
			self.uiactions.delete_page()

		self.assertFalse(self.page.exists())

	def testTrashPageCancel(self):
		self.assertTrue(self.page.exists())

		def cancel_delete(dialog):
			assert isinstance(dialog, TrashPageDialog)
			dialog.do_response_cancel()

		with tests.DialogContext(cancel_delete):
			self.uiactions.delete_page()

		self.assertTrue(self.page.exists())

	def testTrashPageFallbackToDelete(self):
		from zim.newfs.helpers import TrashNotSupportedError
		self.assertTrue(self.page.exists())

		def mock_trash_iter(*a, **k):
			yield
			raise TrashNotSupportedError('Test')
		self.notebook.trash_page_iter = mock_trash_iter

		def fail_trash(dialog):
			assert isinstance(dialog, TrashPageDialog)
			dialog.do_response_ok() # NOT assert_repsonse_ok - we want to fail

		def question_yes(dialog):
			dialog.answer_yes()

		with tests.LoggingFilter('zim', 'Test'):
			with tests.DialogContext(fail_trash, question_yes, DeletePageDialog):
				self.uiactions.delete_page()

		self.assertFalse(self.page.exists())

	def testTrashPageFallbackToDeleteCancel(self):
		from zim.newfs.helpers import TrashNotSupportedError
		self.assertTrue(self.page.exists())

		def mock_trash_iter(*a, **k):
			yield
			raise TrashNotSupportedError('Test')
		self.notebook.trash_page_iter = mock_trash_iter

		def fail_trash(dialog):
			assert isinstance(dialog, TrashPageDialog)
			dialog.do_response_ok() # NOT assert_response_ok - we want to fail

		def question_no(dialog):
			dialog.answer_no()

		with tests.LoggingFilter('zim', 'Test'):
			with tests.DialogContext(fail_trash, question_no):
				self.uiactions.delete_page()

		self.assertTrue(self.page.exists())

	def testDeletePage(self):
		self.notebook.config['Notebook']['disable_trash'] = True
		self.assertTrue(self.page.exists())

		with tests.DialogContext(DeletePageDialog):
			self.uiactions.delete_page()

		self.assertFalse(self.page.exists())

	def testDeletePageAndChildren(self):
		self.notebook.config['Notebook']['disable_trash'] = True
		self.assertTrue(self.page.exists())
		child = self.notebook.get_page(Path('Test:Child'))
		child.parse('wiki', 'Test 123')
		self.notebook.store_page(child)
		dir = self.notebook.get_attachments_dir(self.page)
		self.assertTrue(dir.exists())
		dir.folder('foo').touch()

		with tests.DialogContext(DeletePageDialog):
			self.uiactions.delete_page()

		self.assertFalse(self.page.exists())
		self.assertFalse(dir.exists())

	def testDeletePageCancel(self):
		self.notebook.config['Notebook']['disable_trash'] = True
		self.assertTrue(self.page.exists())

		def cancel_delete(dialog):
			assert isinstance(dialog, DeletePageDialog)
			dialog.do_response_cancel()

		with tests.DialogContext(cancel_delete):
			self.uiactions.delete_page()

		self.assertTrue(self.page.exists())

	def testTrashPageUpdateLinks(self):
		self.assertTrue(self.page.exists())

		referrer = self.notebook.get_page(Path('Referrer'))
		referrer.parse('wiki', 'Test [[Test]]\n')
		self.notebook.store_page(referrer)

		with tests.DialogContext(
				(TrashPageDialog, lambda d: d.update_links_checkbutton.set_active(True))
			):
				self.uiactions.delete_page()

		self.assertFalse(self.page.exists())
		self.assertEqual(referrer.dump('wiki'), ['Test Test\n'])

	def testTrashPageNoUpdateLinks(self):
		self.assertTrue(self.page.exists())

		referrer = self.notebook.get_page(Path('Referrer'))
		referrer.parse('wiki', 'Test [[Test]]\n')
		self.notebook.store_page(referrer)

		with tests.DialogContext(
				(TrashPageDialog, lambda d: d.update_links_checkbutton.set_active(False))
			):
				self.uiactions.delete_page()

		self.assertFalse(self.page.exists())
		self.assertEqual(referrer.dump('wiki'), ['Test [[Test]]\n'])

	def testDeletePageUpdateLinks(self):
		self.notebook.config['Notebook']['disable_trash'] = True
		self.assertTrue(self.page.exists())

		referrer = self.notebook.get_page(Path('Referrer'))
		referrer.parse('wiki', 'Test [[Test]]\n')
		self.notebook.store_page(referrer)

		with tests.DialogContext(
				(DeletePageDialog, lambda d: d.update_links_checkbutton.set_active(True))
			):
				self.uiactions.delete_page()

		self.assertFalse(self.page.exists())
		self.assertEqual(referrer.dump('wiki'), ['Test Test\n'])

	def testDeletePageNoUpdateLinks(self):
		self.notebook.config['Notebook']['disable_trash'] = True
		self.assertTrue(self.page.exists())

		referrer = self.notebook.get_page(Path('Referrer'))
		referrer.parse('wiki', 'Test [[Test]]\n')
		self.notebook.store_page(referrer)

		with tests.DialogContext(
				(DeletePageDialog, lambda d: d.update_links_checkbutton.set_active(False))
			):
				self.uiactions.delete_page()

		self.assertFalse(self.page.exists())
		self.assertEqual(referrer.dump('wiki'), ['Test [[Test]]\n'])

	def testOpenAttachmentsFolderExisting(self):
		folder = self.notebook.get_attachments_dir(self.page)
		folder.touch()

		def open_folder(cmd):
			self.assertEqual(strip_file_url_prefix(cmd[-1]), folder.path)

		with tests.ApplicationContext(open_folder):
			with tests.DialogContext():
				self.uiactions.open_attachments_folder()

	def testOpenAttachmentsFolderNonExisting(self):
		folder = self.notebook.get_attachments_dir(self.page)
		self.assertFalse(folder.exists())

		def create_folder(dialog):
			dialog.answer_yes()

		def open_folder(cmd):
			self.assertEqual(strip_file_url_prefix(cmd[-1]), folder.path)

		with tests.ApplicationContext(open_folder):
			with tests.DialogContext(create_folder):
				self.uiactions.open_attachments_folder()

	def testOpenNotebookFolder(self):
		def open_folder(cmd):
			self.assertEqual(strip_file_url_prefix(cmd[-1]), self.notebook.folder.path)

		with tests.ApplicationContext(open_folder):
			self.uiactions.open_notebook_folder()

	def testOpenDocumentRoot(self):
		from zim.gui.widgets import ErrorDialog
		self.notebook.document_root = self.setUpFolder(mock=tests.MOCK_ALWAYS_REAL)
		self.notebook.document_root.touch()

		def open_folder(cmd):
			self.assertEqual(strip_file_url_prefix(cmd[-1]), self.notebook.document_root.path)

		with tests.ApplicationContext(open_folder):
			with tests.DialogContext():
				self.uiactions.open_document_root()

	def testOpenDocumentRootNotDefined(self):
		from zim.gui.widgets import ErrorDialog

		self.assertIsNone(self.notebook.document_root)

		with tests.LoggingFilter('zim', 'No document root defined'):
			with tests.ApplicationContext():
				with tests.DialogContext(ErrorDialog):
					self.uiactions.open_document_root()

	def testEditPageSource(self):
		from zim.gui.widgets import MessageDialog
		from zim.newfs import LocalFile
		from zim.gui.applications import ApplicationManager

		oldtext = self.page.dump('plain') # trick page into caching content
		signals = tests.SignalLogger(self.page)

		def edit_page(cmd):
			file = LocalFile(cmd[-1])
			self.assertEqual(file, self.page.source_file)
			file.write('New text\n')

		manager = ApplicationManager()
		entry = manager.create('text/plain', 'test', 'test')
		manager.set_default_application('text/plain', entry)

		with tests.ApplicationContext(edit_page):
			with tests.DialogContext(MessageDialog):
				self.uiactions.edit_page_source()

		newtext = self.page.dump('plain')
		self.assertEqual(signals['storage-changed'], [(True,)]) # boolean for external change
		self.assertNotEqual(oldtext, newtext)


class TestManualProperties(tests.TestCase):

	def runTest(self):
		from zim.gui.propertiesdialog import notebook_properties

		with open('./data/manual/Help/Properties.txt') as fh:
			manual = fh.read()

		for pref in notebook_properties:
			label = pref[2]
			if '\n' in label:
				label, x = label.split('\n', 1)
				label = label.rstrip(',')
			self.assertTrue(label in manual, 'Property "%s" not documented in manual page' % label)
