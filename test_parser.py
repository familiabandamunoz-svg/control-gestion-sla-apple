import os
import unittest
from parser_solver import procesar_excel_solver, extraer_responsable_nota, normalizar_nombre


class TestSolverParser(unittest.TestCase):
    def test_normalizacion_nombres(self):
        self.assertEqual(normalizar_nombre('Jeremy Alexander Vera Alarcon'), 'Jeremy Vera')
        self.assertEqual(normalizar_nombre('Sebastian Ignacio Banda Fortini'), 'Sebastián Banda')
        self.assertEqual(normalizar_nombre('Jose Mauricio Vera Vilaza'), 'Jose Vera')
        self.assertEqual(normalizar_nombre(None), 'Sin Asignar')

    def test_extraccion_desde_notas(self):
        nota = "Notas de resolución: Se instala APP.\n\n» Cerrado en 2025-10-08 13:06:59\n» Cerrado por Sebastian Ignacio Banda Fortini\n» Grupo de asignación BCH-GST-APPLE"
        self.assertEqual(extraer_responsable_nota(nota), 'Sebastian Ignacio Banda Fortini')

    def test_procesamiento_excel_real(self):
        excel_path = 'BCH-APPLE-Report Octubre-2026.xlsx'
        if not os.path.exists(excel_path):
            self.skipTest(f"No se encontró {excel_path} en la raíz para prueba de integración")
        registros = procesar_excel_solver(excel_path)
        self.assertEqual(len(registros), 2148)
        inc = [r for r in registros if r['tipo'] == 'Incidente']
        req = [r for r in registros if r['tipo'] == 'Requerimiento']
        self.assertEqual(len(inc), 870)
        self.assertEqual(len(req), 1278)
        asignados = [r for r in registros if r['responsable'] != 'Sin Asignar']
        self.assertGreater(len(asignados) / len(registros), 0.97)


if __name__ == '__main__':
    unittest.main(verbosity=2)
