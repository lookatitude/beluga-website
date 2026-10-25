package main

import (
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"strings"
)

func main() {
	root, mod := os.Args[1], os.Args[2]
	out := map[string]map[string]string{} // importpath -> name -> kind
	pkgname := map[string]string{}
	filepath.Walk(root, func(p string, info os.FileInfo, err error) error {
		if info.IsDir() && (info.Name() == ".git" || info.Name() == "testdata" || info.Name() == ".claude") {
			return filepath.SkipDir
		}
		if info.IsDir() || !strings.HasSuffix(p, ".go") || strings.HasSuffix(p, "_test.go") {
			return nil
		}
		f, err := parser.ParseFile(token.NewFileSet(), p, nil, 0)
		if err != nil {
			return nil
		}
		rel, _ := filepath.Rel(root, filepath.Dir(p))
		ip := mod
		if rel != "." {
			ip = mod + "/" + filepath.ToSlash(rel)
		}
		if out[ip] == nil {
			out[ip] = map[string]string{}
		}
		pkgname[ip] = f.Name.Name
		for _, d := range f.Decls {
			switch d := d.(type) {
			case *ast.FuncDecl:
				if d.Recv == nil && d.Name.IsExported() {
					out[ip][d.Name.Name] = "func"
				}
			case *ast.GenDecl:
				for _, s := range d.Specs {
					switch s := s.(type) {
					case *ast.TypeSpec:
						if s.Name.IsExported() {
							out[ip][s.Name.Name] = "type"
						}
					case *ast.ValueSpec:
						for _, n := range s.Names {
							if n.IsExported() {
								out[ip][n.Name] = "value"
							}
						}
					}
				}
			}
		}
		return nil
	})
	json.NewEncoder(os.Stdout).Encode(map[string]any{"api": out, "names": pkgname})
}
